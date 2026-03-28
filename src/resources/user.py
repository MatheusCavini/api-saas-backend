import falcon
import logging

from controllers.user import UserController
from exception import NotAuthorizedException
from utils.validator import validate_payload
class UserResource:

    auth_required = True

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_get(self, req, resp):
        user_controller = UserController(req.context.db_session)
        self.logger.info("Processing GET request for user context (/me)")
        resp.media = user_controller.get_me(req.context.user)
        resp.status = falcon.HTTP_200
    
    def on_put(self, req, resp):
        user_controller = UserController(req.context.db_session)
        self.logger.info("Processing PUT request for user context (/me)")
        payload = req.media or {}
        validate_payload(payload, "user_update")
        resp.media = user_controller.update_me(req.context.user, payload)
        resp.status = falcon.HTTP_200

    def on_patch(self, req, resp):
        self.on_put(req, resp)