import falcon
import logging

from controllers.verify_account import VerifyAccountController
from utils.validator import validate_payload


import falcon
import logging

class VerifyAccountResource:
    """
    PUBLIC endpoint. Triggered by Page 2 (the processor page) 
    when the user clicks the link from any device.
    """
    auth_required = False  # CRITICAL FIX: Must be accessible without a session!

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_post(self, req, resp):
        data = req.media or {}
        token = data.get("token")

        if not token:
            raise falcon.HTTPBadRequest(
                title="Bad Request",
                description="Verification token is missing from the request body."
            )

        verify_account_controller = VerifyAccountController(req.context.db_session)
        self.logger.info("Processing POST request for account verification (Magic Link)")
        
        # We pass the raw token string, not the user context
        resp.media = verify_account_controller.verify_token(token)
        resp.status = falcon.HTTP_200  # 200 OK is more semantic than 201 Created here


class ResendVerificationResource:
    """
    PROTECTED endpoint. Triggered by Page 1 (the waiting room) 
    when the user clicks 'Resend Email'.
    """
    auth_required = True  # They are logged in, just unverified.

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_post(self, req, resp):
        verify_account_controller = VerifyAccountController(req.context.db_session)
        
        # Fixed the copy-pasted log message!
        self.logger.info("Processing POST request to resend verification link")
        
        # Because auth_required = True, req.context.user exists!
        resp.media = verify_account_controller.resend_link(req.context.user)
        resp.status = falcon.HTTP_200