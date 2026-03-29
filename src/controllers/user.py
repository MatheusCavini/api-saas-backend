import logging
from datetime import datetime, timezone

from exception import NotAuthorizedException, ConflictException
from models.api_key import ApiKey
from models.invitation import Invitation
from models.invitation_status import InvitationStatus
from models.subscription import Subscription
from models.workspace import Workspace
from models.workspace_member import WorkspaceMember
from mappers.user import model_to_response as user_to_response
from mappers.workspace import model_to_response as workspace_to_response
from sqlalchemy.exc import IntegrityError


class UserController:
    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)

    def get_me(self, user) -> dict:
        if user is None:
            self.logger.warning("User context requested without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )

        self.logger.info("Fetching context payload for user_id=%s", user.id)

        # 1. Fetch the user's ACTIVE workspaces and their roles
        memberships = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(Workspace.deactivated_on.is_(None))
            .all()
        )

        workspaces_data = []
        has_active_subscription = False
        has_active_api_key = False

        for membership in memberships:
            workspace = membership.workspace
            ws_payload = workspace_to_response(workspace)
            ws_payload["role"] = membership.role.name if membership.role else None
            
            subscription_status = "inactive"
            has_workspace_active_api_key = False
            now = datetime.now(timezone.utc)
            latest_sub = (
                self.db_session.query(Subscription)
                .filter(Subscription.workspace_id == workspace.id)
                .order_by(Subscription.created_at.desc())
                .first()
            )
            if latest_sub:
                subscription_status = latest_sub.status or "inactive"
                if subscription_status == "active" and latest_sub.current_period_end and latest_sub.current_period_end > now:
                    has_active_subscription = True
                    active_key = (
                        self.db_session.query(ApiKey)
                        .filter(ApiKey.workspace_id == workspace.id)
                        .filter(ApiKey.status == "active")
                        .first()
                    )
                    if active_key:
                        has_workspace_active_api_key = True
                        has_active_api_key = True

            ws_payload["subscription_status"] = subscription_status
            ws_payload["has_active_api_key"] = has_workspace_active_api_key
            workspaces_data.append(ws_payload)

        # 2. Determine the user's routing state for the frontend
        # Check for pending invitation before anything else
        pending_invitation = (
            self.db_session.query(Invitation)
            .join(InvitationStatus)
            .filter(Invitation.invited_email == user.email)
            .filter(InvitationStatus.enum == "pending")
            .first()
        )
        pending_invitation_data = None

        if pending_invitation:
            routing_state = "pending_invitation"
            
            # Serialize the invitation data so the frontend can display it
            pending_invitation_data = {
                "invitation_key": str(pending_invitation.invitation_key),
                "invited_email": pending_invitation.invited_email,
                "host_name": pending_invitation.host_user.username if pending_invitation.host_user else None,
                "workspace_name": pending_invitation.workspace.name if pending_invitation.workspace else None,
                "role_name": pending_invitation.role.name if pending_invitation.role else None,
                "expires_at": pending_invitation.expires_at.isoformat() if pending_invitation.expires_at else None,
                "status": "pending"
            }
        else:
            # Default to dashboard, then downgrade based on missing requirements
            routing_state = "dashboard"
            
            if not workspaces_data:
                routing_state = "create_workspace"
            elif not has_active_subscription:
                routing_state = "plan_selection"
            elif not has_active_api_key:
                routing_state = "api_key_setup"

        # 3. Format the final response payload using our new mapper
        user_data = user_to_response(user)

        self.logger.info(
            "Returning /me payload for user_id=%s with routing_state=%s", 
            user.id, 
            routing_state
        )

        return {
            "user": user_data,
            "workspaces": workspaces_data,
            "routing_state": routing_state,
            "pending_invitation": pending_invitation_data
        }
        
    def update_me(self, user, payload):
        if user is None:
            self.logger.warning("User update requested without authenticated user.")
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Authentication is required.",
            )
    

        new_name = payload.get("name")

        user.username = new_name
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.warning("Registration failed: user already exists")
            raise ConflictException(
                title="Conflict",
                description="A user with this email already exists.",
            ) from exc

        return user_to_response(user)