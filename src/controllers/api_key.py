"""Business logic and DB operations for API keys."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError

from exception import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotAuthorizedException,
    NotFoundException,
)
from mappers.api_key import model_to_response as api_key_to_response
from models.api_key import ApiKey
from models.subscription import Subscription
from models.workspace import Workspace
from models.workspace_member import WorkspaceMember

_api_key_context = CryptContext(schemes=["argon2"], deprecated="auto")


class ApiKeyController:
    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)

    def create(self, payload: dict, user) -> dict:
        if user is None:
            self.logger.warning("API key create attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        membership = self._get_single_membership_for_user(user)
        if membership.role.name not in {"owner", "admin"}:
            self.logger.warning(
                "API key create forbidden for user_id=%s on workspace_id=%s",
                user.id,
                membership.workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="Only workspace owners and admins can create API keys.",
            )

        self._ensure_active_subscription(membership.workspace_id)

        plain_text_key = self._generate_plain_text_key()
        key_prefix = self._prefix_for_display(plain_text_key)
        key_hash = _api_key_context.hash(plain_text_key)

        # NOTE: DB schema currently defines api_keys.name as NOT NULL.
        # We do not require it from the client; we set a safe server default.
        api_key = ApiKey(
            workspace_id=membership.workspace_id,
            name="default",
            key_prefix=key_prefix,
            key_hash=key_hash,
            status="active",
        )

        self.db_session.add(api_key)
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("API key create failed due to integrity error.")
            raise ConflictException(
                title="Conflict",
                description="API key could not be created due to a conflict.",
            ) from exc

        self.db_session.refresh(api_key)
        response = api_key_to_response(api_key)
        response["plain_text_key"] = plain_text_key
        return response

    def get_api_key(self, user, api_key_key: str) -> dict:
        if user is None:
            self.logger.warning("API key get attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        api_key_uuid = self._parse_uuid(api_key_key, field_name="api_key_key")
        api_key = (
            self.db_session.query(ApiKey)
            .filter(ApiKey.api_key_key == api_key_uuid)
            .first()
        )
        if not api_key:
            self.logger.warning("API key not found for api_key_key=%s", api_key_key)
            raise NotFoundException(
                title="Not Found",
                description="API key not found.",
            )

        membership = self._get_membership_for_user_and_workspace(user, api_key.workspace_id)
        if membership.role.name not in {"owner", "admin"}:
            self.logger.warning(
                "API key get forbidden for user_id=%s on workspace_id=%s",
                user.id,
                api_key.workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="Only workspace owners and admins can view API keys.",
            )

        return api_key_to_response(api_key)

    def list_api_keys(self, user) -> list[dict]:
        if user is None:
            self.logger.warning("API key list attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        membership = self._get_single_membership_for_user(user)
        if membership.role.name not in {"owner", "admin"}:
            self.logger.warning(
                "API key list forbidden for user_id=%s on workspace_id=%s",
                user.id,
                membership.workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="Only workspace owners and admins can view API keys.",
            )

        api_keys = (
            self.db_session.query(ApiKey)
            .filter(ApiKey.workspace_id == membership.workspace_id)
            .order_by(ApiKey.created_at.desc())
            .all()
        )
        return [api_key_to_response(api_key) for api_key in api_keys]

    def delete_api_key(self, user, api_key_key: str) -> None:
        if user is None:
            self.logger.warning("API key delete attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        api_key_uuid = self._parse_uuid(api_key_key, field_name="api_key_key")
        api_key = (
            self.db_session.query(ApiKey)
            .filter(ApiKey.api_key_key == api_key_uuid)
            .first()
        )
        if not api_key:
            self.logger.warning("API key not found for api_key_key=%s", api_key_key)
            raise NotFoundException(
                title="Not Found",
                description="API key not found.",
            )

        membership = self._get_membership_for_user_and_workspace(user, api_key.workspace_id)
        if membership.role.name not in {"owner", "admin"}:
            self.logger.warning(
                "API key delete forbidden for user_id=%s on workspace_id=%s",
                user.id,
                api_key.workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="Only workspace owners and admins can revoke API keys.",
            )

        if api_key.status != "revoked":
            api_key.status = "revoked"
            self.db_session.commit()

    def _get_single_membership_for_user(self, user) -> WorkspaceMember:
        memberships = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(Workspace.deactivated_on.is_(None))
            .all()
        )
        if not memberships:
            self.logger.warning("Workspace membership not found for user_id=%s", user.id)
            raise NotFoundException(
                title="Not Found",
                description="Workspace not found.",
            )
        if len(memberships) > 1:
            self.logger.warning(
                "Multiple workspaces found for user_id=%s; cannot infer workspace.",
                user.id,
            )
            raise BadRequestException(
                title="Bad Request",
                description="Multiple workspaces found. Provide workspace_key.",
            )
        return memberships[0]

    def _ensure_active_subscription(self, workspace_id: int) -> None:
        now = datetime.now(timezone.utc)
        subscription = (
            self.db_session.query(Subscription)
            .filter(Subscription.workspace_id == workspace_id)
            .filter(Subscription.status == "active")
            .filter(Subscription.current_period_end > now)
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if not subscription:
            self.logger.warning(
                "API key create blocked: no active subscription for workspace_id=%s",
                workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="An active subscription is required to create API keys.",
            )

    def _get_membership_for_user_and_workspace(self, user, workspace_id: int) -> WorkspaceMember:
        membership = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(WorkspaceMember.workspace_id == workspace_id)
            .filter(Workspace.deactivated_on.is_(None))
            .first()
        )
        if not membership:
            self.logger.warning(
                "Workspace membership not found for user_id=%s workspace_id=%s",
                user.id,
                workspace_id,
            )
            raise NotFoundException(
                title="Not Found",
                description="Workspace not found.",
            )
        return membership

    def _parse_uuid(self, value: str, field_name: str) -> UUID:
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as exc:
            self.logger.warning("Invalid %s=%s provided.", field_name, value)
            raise BadRequestException(
                title="Bad Request",
                description=f"Invalid {field_name}.",
            ) from exc

    def _generate_plain_text_key(self) -> str:
        # Stateless: generate once, return once, store only prefix+hash.
        return f"sk_live_{secrets.token_urlsafe(32)}"

    def _prefix_for_display(self, plain_text_key: str) -> str:
        prefix_len = 15
        if len(plain_text_key) <= prefix_len:
            return plain_text_key
        return f"{plain_text_key[:prefix_len]}..."
