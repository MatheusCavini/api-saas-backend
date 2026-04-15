"""Business logic and DB operations for workspaces."""
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from exception import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotAuthorizedException,
    NotFoundException,
    ServiceUnavailableException,
)
from controllers.stripe import StripeController
from mappers.workspace_member import model_to_response as workspace_member_to_response
from mappers.workspace import model_to_response as workspace_to_response
from models.api_key import ApiKey
from models.invitation import Invitation
from models.invitation_status import InvitationStatus
from models.role import Role
from models.user import User
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

        workspace_id = membership.workspace_id
        workspace = membership.workspace

        self.logger.info(
            "Deleting workspace_id=%s for user_id=%s", workspace_id, user.id
        )

        expired_status = self._get_invitation_status_by_enum("expired")
        pending_status = self._get_invitation_status_by_enum("pending")
        deleted_at = datetime.now(timezone.utc)

        try:
            StripeController(self.db_session).cancel_workspace_subscription(workspace_id)

            #Revoke API Keys from that workspace
            (
                self.db_session.query(ApiKey)
                .filter(ApiKey.workspace_id == workspace_id)
                .filter(ApiKey.status != "revoked")
                .update({"status": "revoked"}, synchronize_session=False)
            )

            # Expires (soft delete) invitations from workspace
            (
                self.db_session.query(Invitation)
                .filter(Invitation.workspace_id == workspace_id)
                .filter(Invitation.status_id == pending_status.id)
                .update({"status_id": expired_status.id}, synchronize_session=False)
            )

            workspace.deactivated_on = deleted_at
            workspace.stripe_customer_id = None

            self.db_session.commit()
        except Exception:
            self.db_session.rollback()
            self.logger.exception(
                "Workspace deletion failed for workspace_id=%s user_id=%s",
                workspace_id,
                user.id,
            )
            raise
        self.logger.info(
            "Workspace deactivated workspace_id=%s for user_id=%s",
            workspace_id,
            user.id,
        )

    def list_members_for_user(self, user, workspace_key: str | None = None) -> list[dict]:
        if user is None:
            self.logger.warning("Workspace member list attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        membership = self._get_membership_for_user(user, workspace_key)
        members = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .join(User)
            .filter(WorkspaceMember.workspace_id == membership.workspace_id)
            .filter(Workspace.deactivated_on.is_(None))
            .order_by(func.lower(User.username).asc(), User.id.asc())
            .all()
        )
        self.logger.info(
            "Found %s workspace members for workspace_id=%s requested by user_id=%s",
            len(members),
            membership.workspace_id,
            user.id,
        )
        return [workspace_member_to_response(member) for member in members]

    def update_member_role_for_user(
        self,
        user,
        payload: dict,
        workspace_key: str | None = None,
    ) -> dict:
        if user is None:
            self.logger.warning("Workspace member role update attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        acting_membership = self._get_membership_for_user(user, workspace_key)
        self._ensure_admin_or_owner(acting_membership, action="manage workspace members")

        target_membership = self._get_workspace_member_by_user_key(
            workspace_id=acting_membership.workspace_id,
            user_key=payload.get("user_key"),
        )
        role = self._get_role_by_key(payload.get("role_key"))

        if role.name == "owner":
            raise ForbiddenException(
                title="Forbidden",
                description="Owner role cannot be assigned through workspace membership updates.",
            )
        if target_membership.role.name == "owner":
            raise ForbiddenException(
                title="Forbidden",
                description="Workspace owner membership cannot be modified.",
            )

        target_membership.role = role
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Workspace member role update failed due to integrity error.")
            raise ConflictException(
                title="Conflict",
                description="Workspace member role could not be updated due to a conflict.",
            ) from exc

        self.db_session.refresh(target_membership)
        self.logger.info(
            "Updated workspace member role for workspace_id=%s target_user_id=%s by user_id=%s",
            acting_membership.workspace_id,
            target_membership.user_id,
            user.id,
        )
        return workspace_member_to_response(target_membership)

    def delete_member_for_user(
        self,
        user,
        target_user_key: str | None,
        workspace_key: str | None = None,
    ) -> None:
        if user is None:
            self.logger.warning("Workspace member delete attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        acting_membership = self._get_membership_for_user(user, workspace_key)
        self._ensure_admin_or_owner(acting_membership, action="manage workspace members")

        target_membership = self._get_workspace_member_by_user_key(
            workspace_id=acting_membership.workspace_id,
            user_key=target_user_key,
        )
        if target_membership.role.name == "owner":
            raise ForbiddenException(
                title="Forbidden",
                description="Workspace owner membership cannot be revoked.",
            )

        self.db_session.delete(target_membership)
        self.db_session.commit()
        self.logger.info(
            "Revoked workspace membership for workspace_id=%s target_user_id=%s by user_id=%s",
            acting_membership.workspace_id,
            target_membership.user_id,
            user.id,
        )

    def _ensure_admin_or_owner(self, membership: WorkspaceMember, action: str) -> None:
        if membership.role.name in {"owner", "admin"}:
            return
        self.logger.warning(
            "Workspace action forbidden for user_id=%s on workspace_id=%s",
            membership.user_id,
            membership.workspace_id,
        )
        raise ForbiddenException(
            title="Forbidden",
            description=f"Only workspace owners and admins can {action}.",
        )

    def _get_workspace_member_by_user_key(
        self,
        workspace_id: int,
        user_key: str | None,
    ) -> WorkspaceMember:
        if not user_key:
            raise BadRequestException(
                title="Bad Request",
                description="user_key is required.",
            )

        user_uuid = self._parse_uuid(user_key, field_name="user_key")
        membership = (
            self.db_session.query(WorkspaceMember)
            .join(User)
            .join(Workspace)
            .filter(WorkspaceMember.workspace_id == workspace_id)
            .filter(User.user_key == user_uuid)
            .filter(Workspace.deactivated_on.is_(None))
            .first()
        )
        if membership is None:
            raise NotFoundException(
                title="Not Found",
                description="Workspace member not found.",
            )
        return membership

    def _get_role_by_key(self, role_key: str | None) -> Role:
        if not role_key:
            raise BadRequestException(
                title="Bad Request",
                description="role_key is required.",
            )

        role_uuid = self._parse_uuid(role_key, field_name="role_key")
        role = self.db_session.query(Role).filter(Role.role_key == role_uuid).first()
        if role is None:
            raise NotFoundException(
                title="Not Found",
                description="Role not found.",
            )
        return role

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

    def _parse_uuid(self, value: str, field_name: str) -> UUID:
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as exc:
            self.logger.warning("Invalid %s=%s provided.", field_name, value)
            raise BadRequestException(
                title="Bad Request",
                description=f"Invalid {field_name}.",
            ) from exc

    def _get_invitation_status_by_enum(self, enum_value: str) -> InvitationStatus:
        status = (
            self.db_session.query(InvitationStatus)
            .filter(InvitationStatus.enum == enum_value)
            .first()
        )
        if status is None:
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description=f"Invitation status '{enum_value}' is not configured.",
            )
        return status
