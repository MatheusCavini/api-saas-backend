import falcon
import logging

from controllers.user import UserController
from exception import NotAuthorizedException

class UserResource:

    auth_required = True

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_get(self, req, resp):
        user_controller = UserController(req.context.db_session)
        self.logger.info("Processing GET request for user context (/me)")
        
        resp.media = user_controller.get_me(req.context.user)
        resp.status = falcon.HTTP_200