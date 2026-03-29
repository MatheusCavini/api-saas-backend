"""Business logic and DB operations for invitations."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
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
from mappers.invitation import model_to_response as invitation_to_response
from mappers.role import model_to_response as role_to_response
from mappers.user import model_to_response as user_to_response
from mappers.workspace import model_to_response as workspace_to_response
from models.invitation import Invitation
from models.invitation_status import InvitationStatus
from models.role import Role
from models.user import User
from models.workspace import Workspace
from models.workspace_member import WorkspaceMember


class InvitationController:
    INVITATION_EXPIRY_PERIOD = timedelta(days=7)

    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)

    def create(self, payload: dict, user) -> dict:
        if user is None:
            self.logger.warning("Invitation create attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        membership = self._get_membership_for_user(user, payload.get("workspace_key"))
        self._ensure_admin_or_owner(membership, action="create invitations")

        invited_email = self._normalize_email(payload.get("invited_email"))
        role = self._get_role_by_key(payload.get("role_key"))
        if role.name == "owner":
            raise ForbiddenException(
                title="Forbidden",
                description="Owner role cannot be assigned through invitations.",
            )

        existing_user = self._get_user_by_email(invited_email)
        if existing_user is not None and self._user_has_active_workspace(existing_user.id):
            raise ConflictException(
                title="Conflict",
                description="An invitation cannot be created for a user who already belongs to a workspace.",
            )

        self._expire_pending_invitations(workspace_id=membership.workspace_id, invited_email=invited_email)
        pending_status = self._get_status_by_enum("pending")
        duplicate_pending = (
            self.db_session.query(Invitation)
            .join(InvitationStatus)
            .filter(Invitation.workspace_id == membership.workspace_id)
            .filter(func.lower(Invitation.invited_email) == invited_email)
            .filter(InvitationStatus.enum == "pending")
            .first()
        )
        if duplicate_pending:
            raise ConflictException(
                title="Conflict",
                description="A pending invitation already exists for this email in the workspace.",
            )

        invitation = Invitation(
            workspace_id=membership.workspace_id,
            invited_email=invited_email,
            host_user_id=user.id,
            role_id=role.id,
            status_id=pending_status.id,
            expires_at=self._now() + self.INVITATION_EXPIRY_PERIOD,
        )
        self.db_session.add(invitation)
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Invitation create failed due to integrity error.")
            raise ConflictException(
                title="Conflict",
                description="Invitation could not be created due to a conflict.",
            ) from exc

        self.db_session.refresh(invitation)
        payload = self._serialize_invitation(invitation)
        if existing_user is not None:
            payload["invited_user"] = user_to_response(existing_user)
        return payload

    def list_for_workspace(self, user) -> list[dict]:
        if user is None:
            self.logger.warning("Invitation list attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        membership = self._get_single_membership_for_user(user)
        self._ensure_admin_or_owner(membership, action="view invitations")
        self._expire_pending_invitations(workspace_id=membership.workspace_id)

        invitations = (
            self.db_session.query(Invitation)
            .filter(Invitation.workspace_id == membership.workspace_id)
            .order_by(Invitation.created_at.desc())
            .all()
        )
        return [self._serialize_invitation(invitation) for invitation in invitations]

    def delete(self, user, invitation_key: str | None) -> None:
        if user is None:
            self.logger.warning("Invitation revoke attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        invitation = self._get_invitation_by_key(invitation_key)
        membership = self._get_membership_for_user_and_workspace(user, invitation.workspace_id)
        self._ensure_admin_or_owner(membership, action="revoke invitations")
        self._expire_invitation_if_needed(invitation)

        if invitation.status.enum == "revoked":
            return
        if invitation.status.enum == "expired":
            raise ConflictException(
                title="Conflict",
                description="Invitation has expired.",
            )
        if invitation.status.enum != "pending":
            raise ConflictException(
                title="Conflict",
                description="Only pending invitations can be revoked.",
            )

        invitation.status = self._get_status_by_enum("revoked")
        self.db_session.commit()

    def accept(self, user, invitation_key: str | None) -> dict:
        if user is None:
            self.logger.warning("Invitation accept attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        self._ensure_user_has_no_active_workspace_membership(user)
        invitation = self._get_invitation_by_key(invitation_key)
        self._ensure_invited_user_matches(invitation, user)
        self._expire_invitation_if_needed(invitation)
        self._ensure_pending_status(invitation, action="accepted")

        membership = WorkspaceMember(
            workspace_id=invitation.workspace_id,
            user_id=user.id,
            role_id=invitation.role_id,
        )
        invitation.status = self._get_status_by_enum("accepted")
        self.db_session.add(membership)
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Invitation accept failed due to integrity error.")
            raise ConflictException(
                title="Conflict",
                description="Invitation could not be accepted due to a conflict.",
            ) from exc

        self.db_session.refresh(invitation)
        return self._serialize_invitation(invitation, invited_user=user)

    def refuse(self, user, invitation_key: str | None) -> dict:
        if user is None:
            self.logger.warning("Invitation refuse attempted without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        self._ensure_user_has_no_active_workspace_membership(user)
        invitation = self._get_invitation_by_key(invitation_key)
        self._ensure_invited_user_matches(invitation, user)
        self._expire_invitation_if_needed(invitation)
        self._ensure_pending_status(invitation, action="refused")

        invitation.status = self._get_status_by_enum("refused")
        self.db_session.commit()
        self.db_session.refresh(invitation)
        return self._serialize_invitation(invitation, invited_user=user)

    def _serialize_invitation(self, invitation: Invitation, invited_user: User | None = None) -> dict:
        payload = invitation_to_response(invitation)
        payload["workspace"] = workspace_to_response(invitation.workspace)
        payload["host_user"] = user_to_response(invitation.host_user)
        payload["role"] = role_to_response(invitation.role)
        payload["status"] = {
            "status_key": str(invitation.status.status_key),
            "enum": invitation.status.enum,
            "description": invitation.status.description,
            "created_at": invitation.status.created_at.isoformat(),
        }

        if invited_user is None:
            invited_user = self._get_user_by_email(invitation.invited_email)
        if invited_user is not None:
            payload["invited_user"] = user_to_response(invited_user)

        return payload

    def _ensure_admin_or_owner(self, membership: WorkspaceMember, action: str) -> None:
        if membership.role.name in {"owner", "admin"}:
            return
        self.logger.warning(
            "Invitation action forbidden for user_id=%s on workspace_id=%s",
            membership.user_id,
            membership.workspace_id,
        )
        raise ForbiddenException(
            title="Forbidden",
            description=f"Only workspace owners and admins can {action}.",
        )

    def _get_single_membership_for_user(self, user) -> WorkspaceMember:
        memberships = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(Workspace.deactivated_on.is_(None))
            .all()
        )
        if not memberships:
            raise NotFoundException(
                title="Not Found",
                description="Workspace not found.",
            )
        if len(memberships) > 1:
            raise BadRequestException(
                title="Bad Request",
                description="Multiple workspaces found. Provide workspace_key.",
            )
        return memberships[0]

    def _ensure_user_has_no_active_workspace_membership(self, user) -> None:
        if self._user_has_active_workspace(user.id):
            raise ConflictException(
                title="Conflict",
                description="Only users without an active workspace can accept or refuse invitations.",
            )

    def _ensure_invited_user_matches(self, invitation: Invitation, user: User) -> None:
        if invitation.invited_email.lower() == user.email.lower():
            return
        raise ForbiddenException(
            title="Forbidden",
            description="This invitation was not issued for the authenticated user.",
        )

    def _ensure_pending_status(self, invitation: Invitation, action: str) -> None:
        if invitation.status.enum == "expired":
            raise ConflictException(
                title="Conflict",
                description="Invitation has expired.",
            )
        if invitation.status.enum != "pending":
            raise ConflictException(
                title="Conflict",
                description=f"Only pending invitations can be {action}.",
            )

    def _expire_pending_invitations(
        self,
        workspace_id: int | None = None,
        invited_email: str | None = None,
    ) -> None:
        expired_status = self._get_status_by_enum("expired")
        query = (
            self.db_session.query(Invitation)
            .join(InvitationStatus)
            .filter(InvitationStatus.enum == "pending")
            .filter(Invitation.expires_at <= self._now())
        )
        if workspace_id is not None:
            query = query.filter(Invitation.workspace_id == workspace_id)
        if invited_email:
            query = query.filter(func.lower(Invitation.invited_email) == invited_email.lower())

        invitations = query.all()
        if not invitations:
            return

        for invitation in invitations:
            invitation.status_id = expired_status.id
        self.db_session.commit()

    def _expire_invitation_if_needed(self, invitation: Invitation) -> None:
        if invitation.status.enum != "pending":
            return
        if invitation.expires_at > self._now():
            return

        invitation.status = self._get_status_by_enum("expired")
        self.db_session.commit()
        self.db_session.refresh(invitation)
        raise ConflictException(
            title="Conflict",
            description="Invitation has expired.",
        )

    def _get_membership_for_user(self, user, workspace_key: str | None) -> WorkspaceMember:
        query = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(Workspace.deactivated_on.is_(None))
        )

        if workspace_key:
            query = query.filter(Workspace.workspace_key == self._parse_uuid(workspace_key, "workspace_key"))

        memberships = query.all()
        if not memberships:
            raise NotFoundException(
                title="Not Found",
                description="Workspace not found.",
            )
        if workspace_key is None and len(memberships) > 1:
            raise BadRequestException(
                title="Bad Request",
                description="Multiple workspaces found. Provide workspace_key.",
            )
        return memberships[0]

    def _get_membership_for_user_and_workspace(self, user, workspace_id: int) -> WorkspaceMember:
        membership = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(WorkspaceMember.workspace_id == workspace_id)
            .filter(Workspace.deactivated_on.is_(None))
            .first()
        )
        if membership is None:
            raise NotFoundException(
                title="Not Found",
                description="Workspace not found.",
            )
        return membership

    def _get_invitation_by_key(self, invitation_key: str | None) -> Invitation:
        if not invitation_key:
            raise BadRequestException(
                title="Bad Request",
                description="invitation_key is required.",
            )

        invitation_uuid = self._parse_uuid(invitation_key, "invitation_key")
        invitation = (
            self.db_session.query(Invitation)
            .join(Workspace)
            .filter(Invitation.invitation_key == invitation_uuid)
            .filter(Workspace.deactivated_on.is_(None))
            .first()
        )
        if invitation is None:
            raise NotFoundException(
                title="Not Found",
                description="Invitation not found.",
            )
        return invitation

    def _get_role_by_key(self, role_key: str | None) -> Role:
        if not role_key:
            raise BadRequestException(
                title="Bad Request",
                description="role_key is required.",
            )

        role_uuid = self._parse_uuid(role_key, "role_key")
        role = self.db_session.query(Role).filter(Role.role_key == role_uuid).first()
        if role is None:
            raise NotFoundException(
                title="Not Found",
                description="Role not found.",
            )
        return role

    def _get_status_by_enum(self, enum_value: str) -> InvitationStatus:
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

    def _get_user_by_email(self, email: str | None) -> User | None:
        if not email:
            return None
        return (
            self.db_session.query(User)
            .filter(func.lower(User.email) == email.lower())
            .first()
        )

    def _normalize_email(self, value: str | None) -> str:
        email = str(value or "").strip().lower()
        if not email:
            raise BadRequestException(
                title="Bad Request",
                description="invited_email is required.",
            )
        return email

    def _parse_uuid(self, value: str, field_name: str) -> UUID:
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise BadRequestException(
                title="Bad Request",
                description=f"Invalid {field_name}.",
            ) from exc

    def _user_has_active_workspace(self, user_id: int) -> bool:
        membership = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user_id)
            .filter(Workspace.deactivated_on.is_(None))
            .first()
        )
        return membership is not None

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
