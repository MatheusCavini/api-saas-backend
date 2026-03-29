"""Falcon resource for RoleController operations."""
import falcon
import logging

from controllers.role import RoleController


class RoleResource:
    auth_required = True
    admin_required = False

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_get(self, req, resp):
        role_controller = RoleController(req.context.db_session)
        self.logger.info("Processing GET request for available roles")
        resp.media = role_controller.list_available()
        resp.status = falcon.HTTP_200
