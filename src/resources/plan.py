"""Falcon resource for PlanController operations."""
import falcon
import logging

from controllers.plan import PlanController
from exception import BadRequestException
from utils.validator import validate_payload


class PlanResource:

    auth_required = True
    admin_required = False

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_get(self, req, resp):
        plan_controller = PlanController(req.context.db_session)
        self.logger.info("Processing GET request for plans")
        resp.media = plan_controller.list_active()
        resp.status = falcon.HTTP_200

