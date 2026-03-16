import logging

from exception import NotAuthorizedException
from models.workspace import Workspace
from models.workspace_member import WorkspaceMember
from mappers.user import model_to_response as user_to_response
from mappers.workspace import model_to_response as workspace_to_response


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

        for membership in memberships:
            workspace = membership.workspace
            ws_payload = workspace_to_response(workspace)
            ws_payload["role"] = membership.role.name if membership.role else None
            
            # --- SUBSCRIPTION CHECK LOGIC ---
            # Assuming your Workspace model has a 'subscription' relationship
            # and that subscription has a 'status' field.
            subscription_status = "inactive"
            if hasattr(workspace, 'subscription') and workspace.subscription:
                subscription_status = workspace.subscription.status
                
                # Treat 'active' and 'trialing' as valid states to access the dashboard
                if subscription_status in ["active", "trialing"]:
                    has_active_subscription = True

            ws_payload["subscription_status"] = subscription_status
            workspaces_data.append(ws_payload)

        # 2. Determine the user's routing state for the frontend
        # Default to dashboard, then downgrade based on missing requirements
        routing_state = "dashboard"
        
        if not workspaces_data:
            routing_state = "create_workspace"
        elif not has_active_subscription:
            routing_state = "plan_selection"

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
            "routing_state": routing_state
        }