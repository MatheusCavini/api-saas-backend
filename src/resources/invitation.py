"""Falcon resource for invitation operations."""
import logging

import falcon

from controllers.invitation import InvitationController
from utils.validator import validate_payload


class InvitationResource:
    auth_required = True

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_post(self, req, resp):
        invitation_controller = InvitationController(req.context.db_session)
        self.logger.info("Processing POST request for invitation creation")
        payload = req.media or {}
        validate_payload(payload, "invitation_create")
        resp.media = invitation_controller.create(payload, req.context.user)
        resp.status = falcon.HTTP_201

    def on_get(self, req, resp):
        invitation_controller = InvitationController(req.context.db_session)
        self.logger.info("Processing GET request for invitation list")
        resp.media = invitation_controller.list_for_workspace(req.context.user)
        resp.status = falcon.HTTP_200

    def on_delete(self, req, resp):
        invitation_controller = InvitationController(req.context.db_session)
        self.logger.info("Processing DELETE request for invitation revoke")
        payload = req.media or {}
        invitation_key = self._get_invitation_key(req, payload)
        validate_payload({"invitation_key": invitation_key}, "invitation_delete")
        invitation_controller.delete(req.context.user, invitation_key)
        resp.status = falcon.HTTP_204

    def on_post_accept(self, req, resp):
        invitation_controller = InvitationController(req.context.db_session)
        self.logger.info("Processing POST request for invitation accept")
        payload = req.media or {}
        invitation_key = self._get_invitation_key(req, payload)
        validate_payload({"invitation_key": invitation_key}, "invitation_action")
        resp.media = invitation_controller.accept(req.context.user, invitation_key)
        resp.status = falcon.HTTP_200

    def on_post_refuse(self, req, resp):
        invitation_controller = InvitationController(req.context.db_session)
        self.logger.info("Processing POST request for invitation refuse")
        payload = req.media or {}
        invitation_key = self._get_invitation_key(req, payload)
        validate_payload({"invitation_key": invitation_key}, "invitation_action")
        resp.media = invitation_controller.refuse(req.context.user, invitation_key)
        resp.status = falcon.HTTP_200

    def _get_invitation_key(self, req, payload: dict) -> str | None:
        if isinstance(payload, dict):
            key = payload.get("invitation_key")
            if key:
                return str(key)
        key = req.get_param("invitation_key")
        if key:
            return str(key)
        return None
