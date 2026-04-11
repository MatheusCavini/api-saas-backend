"""Falcon resource for workspace operations."""
import falcon
import logging

from controllers.workspace import WorkspaceController
from utils.validator import validate_payload


class WorkspaceResource:

    auth_required = True

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_post(self, req, resp):
        workspace_controller = WorkspaceController(req.context.db_session)
        self.logger.info("Processing POST request for workspace")
        payload = req.media or {}
        validate_payload(payload, "workspace_create")
        resp.media = workspace_controller.create(payload, req.context.user)
        resp.status = falcon.HTTP_201

    def on_get(self, req, resp):
        workspace_controller = WorkspaceController(req.context.db_session)
        self.logger.info("Processing GET request for workspace memberships")
        resp.media = workspace_controller.list_for_user(req.context.user)
        resp.status = falcon.HTTP_200

    def on_put(self, req, resp):
        workspace_controller = WorkspaceController(req.context.db_session)
        self.logger.info("Processing PUT request for workspace")
        payload = req.media or {}
        validate_payload(payload, "workspace_update")
        workspace_key = self._get_workspace_key(req, payload)
        resp.media = workspace_controller.update_for_user(req.context.user, payload, workspace_key)
        resp.status = falcon.HTTP_200

    def on_patch(self, req, resp):
        self.on_put(req, resp)

    def on_delete(self, req, resp):
        workspace_controller = WorkspaceController(req.context.db_session)
        self.logger.info("Processing DELETE request for workspace")
        payload = req.media or {}
        validate_payload(payload, "workspace_update")
        workspace_key = self._get_workspace_key(req, payload)
        workspace_controller.delete_for_user(req.context.user, workspace_key)
        resp.status = falcon.HTTP_204

    def on_get_member(self, req, resp):
        workspace_controller = WorkspaceController(req.context.db_session)
        self.logger.info("Processing GET request for workspace member list")
        workspace_key = self._get_workspace_key(req, {})
        resp.media = workspace_controller.list_members_for_user(req.context.user, workspace_key)
        resp.status = falcon.HTTP_200

    def on_put_member(self, req, resp):
        workspace_controller = WorkspaceController(req.context.db_session)
        self.logger.info("Processing PUT request for workspace member role update")
        payload = req.media or {}
        workspace_key = self._get_workspace_key(req, payload)
        user_key = self._get_user_key(req, payload)
        validate_payload(
            {
                "workspace_key": workspace_key,
                "user_key": user_key,
                "role_key": payload.get("role_key"),
            },
            "workspace_member_update",
        )
        resp.media = workspace_controller.update_member_role_for_user(
            req.context.user,
            {
                "user_key": user_key,
                "role_key": payload.get("role_key"),
            },
            workspace_key,
        )
        resp.status = falcon.HTTP_200

    def on_delete_member(self, req, resp):
        workspace_controller = WorkspaceController(req.context.db_session)
        self.logger.info("Processing DELETE request for workspace member revoke")
        payload = req.media or {}
        workspace_key = self._get_workspace_key(req, payload)
        user_key = self._get_user_key(req, payload)
        validate_payload(
            {
                "workspace_key": workspace_key,
                "user_key": user_key,
            },
            "workspace_member_delete",
        )
        workspace_controller.delete_member_for_user(req.context.user, user_key, workspace_key)
        resp.status = falcon.HTTP_204

    def _get_workspace_key(self, req, payload: dict) -> str | None:
        if isinstance(payload, dict):
            key = payload.get("workspace_key")
            if key:
                return str(key)
        key = req.get_param("workspace_key")
        if key:
            return str(key)
        return None

    def _get_user_key(self, req, payload: dict) -> str | None:
        if isinstance(payload, dict):
            key = payload.get("user_key")
            if key:
                return str(key)
        key = req.get_param("user_key")
        if key:
            return str(key)
        return None
