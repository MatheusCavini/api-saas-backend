"""Falcon resource for PlanController operations."""
import falcon
import logging

from controllers.plan import PlanController
from exception import BadRequestException
from utils.validator import validate_payload


class AdminPlanResource:

    auth_required = True
    admin_required = True

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_post(self, req, resp):
        plan_controller = PlanController(req.context.db_session)
        self.logger.info("Processing POST request for plan")
        payload = req.media or {}
        validate_payload(payload, "plan_create")
        resp.media = plan_controller.create(payload)
        resp.status = falcon.HTTP_201

    def on_get(self, req, resp):
        plan_controller = PlanController(req.context.db_session)
        self.logger.info("Processing GET request for plans")
        resp.media = plan_controller.list_active()
        resp.status = falcon.HTTP_200

    def on_put(self, req, resp):
        plan_controller = PlanController(req.context.db_session)
        self.logger.info("Processing PUT request for plan")
        payload = req.media or {}
        validate_payload(payload, "plan_update")
        plan_key = self._get_plan_key(req, payload)
        resp.media = plan_controller.update(payload, plan_key)
        resp.status = falcon.HTTP_200

    def on_patch(self, req, resp):
        self.on_put(req, resp)

    def on_delete(self, req, resp):
        plan_controller = PlanController(req.context.db_session)
        self.logger.info("Processing DELETE request for plan")
        payload = req.media or {}
        plan_key = self._get_plan_key(req, payload)
        plan_controller.delete(plan_key)
        resp.status = falcon.HTTP_204

    def _get_plan_key(self, req, payload: dict) -> str | None:
        if isinstance(payload, dict):
            key = payload.get("plan_key")
            if key:
                return str(key)
        key = req.get_param("plan_key")
        if key:
            return str(key)
        return None
