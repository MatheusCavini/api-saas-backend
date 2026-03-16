"""Business logic and DB operations for workspaces."""
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from exception import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotAuthorizedException,
    NotFoundException,
    ServiceUnavailableException,
)
from mappers.workspace import model_to_response as workspace_to_response
from models.role import Role
from models.workspace import Workspace
from models.workspace_member import WorkspaceMember


class WorkspaceController():
    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)

    def create(self, payload: dict, user) -> dict:
        if user is None:
            self.logger.warning("Workspace create attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authenticated user is required to create a workspace.",
            )

        owner_role = self.db_session.query(Role).filter(Role.name == "owner").first()
        if not owner_role:
            self.logger.error("Workspace create failed: owner role not configured.")
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Workspace owner role is not configured.",
            )

        self.logger.info("Creating workspace for user_id=%s", user.id)
        workspace = Workspace(
            name=payload.get("name"),
        )
        membership = WorkspaceMember(
            workspace=workspace,
            user=user,
            role=owner_role,
        )
        self.db_session.add(workspace)
        self.db_session.add(membership)
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Workspace create failed due to integrity error.")
            raise ConflictException(
                title="Conflict",
                description="Workspace already exists.",
            ) from exc
        self.db_session.refresh(workspace)
        self.logger.info("Workspace created with id=%s for user_id=%s", workspace.id, user.id)
        return workspace_to_response(workspace)

    def list_for_user(self, user) -> list[dict]:
        if user is None:
            self.logger.warning("Workspace list attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        memberships = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(Workspace.deactivated_on.is_(None))
            .all()
        )
        self.logger.info("Found %s workspaces for user_id=%s", len(memberships), user.id)
        return [workspace_to_response(membership.workspace) for membership in memberships]

    def update_for_user(self, user, payload: dict, workspace_key: str | None = None) -> dict:
        if user is None:
            self.logger.warning("Workspace update attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        if "name" not in payload or not str(payload.get("name", "")).strip():
            raise BadRequestException(
                title="Bad Request",
                description="Workspace name is required.",
            )

        membership = self._get_membership_for_user(user, workspace_key)
        if membership.role.name != "owner":
            self.logger.warning(
                "Workspace update forbidden for user_id=%s on workspace_id=%s",
                user.id,
                membership.workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="Only workspace owners can update the workspace.",
            )

        self.logger.info(
            "Updating workspace_id=%s for user_id=%s", membership.workspace_id, user.id
        )
        membership.workspace.name = payload["name"].strip()
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Workspace update failed due to integrity error.")
            raise ConflictException(
                title="Conflict",
                description="Workspace could not be updated due to a conflict.",
            ) from exc
        self.db_session.refresh(membership.workspace)
        self.logger.info(
            "Workspace updated workspace_id=%s for user_id=%s",
            membership.workspace_id,
            user.id,
        )
        return workspace_to_response(membership.workspace)

    def delete_for_user(self, user, workspace_key: str | None = None) -> None:
        if user is None:
            self.logger.warning("Workspace delete attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        membership = self._get_membership_for_user(user, workspace_key)
        if membership.role.name != "owner":
            self.logger.warning(
                "Workspace delete forbidden for user_id=%s on workspace_id=%s",
                user.id,
                membership.workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="Only workspace owners can delete the workspace.",
            )

        self.logger.info(
            "Deleting workspace_id=%s for user_id=%s", membership.workspace_id, user.id
        )
        membership.workspace.deactivated_on = datetime.now(timezone.utc)
        self.db_session.commit()
        self.logger.info(
            "Workspace deactivated workspace_id=%s for user_id=%s",
            membership.workspace_id,
            user.id,
        )

    def _get_membership_for_user(self, user, workspace_key: str | None) -> WorkspaceMember:
        query = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(Workspace.deactivated_on.is_(None))
        )

        if workspace_key:
            try:
                workspace_uuid = UUID(str(workspace_key))
            except (TypeError, ValueError) as exc:
                self.logger.warning("Invalid workspace_key=%s provided.", workspace_key)
                raise BadRequestException(
                    title="Bad Request",
                    description="Invalid workspace_key.",
                ) from exc
            query = query.filter(Workspace.workspace_key == workspace_uuid)

        memberships = query.all()
        if not memberships:
            self.logger.warning("Workspace membership not found for user_id=%s", user.id)
            raise NotFoundException(
                title="Not Found",
                description="Workspace not found.",
            )

        if not workspace_key and len(memberships) > 1:
            self.logger.warning(
                "Multiple workspaces found for user_id=%s; workspace_key required.",
                user.id,
            )
            raise BadRequestException(
                title="Bad Request",
                description="Multiple workspaces found. Provide workspace_key.",
            )

        return memberships[0]
