"""Verify Account controller functions."""
from __future__ import annotations

import logging
import os
import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Adjust these imports to match your project's directory structure
from controllers.auth import (
    _get_jwt_secret, 
    _get_jwt_algorithm, 
    create_verification_token
)
from connectors.resend_connector import send_verification_email
from exception import ConflictException, NotAuthorizedException, ServiceUnavailableException
from models.user import User

class VerifyAccountController:
    def __init__(self, session: Session):
        self.session = session
        self.logger = logging.getLogger(__name__)

    def verify_token(self, token: str) -> dict:
        """
        Validates the magic link token and marks the user as verified.
        """
        self.logger.info("Attempting to verify email token")

        # 1. Decode and Validate the JWT
        try:
            payload = jwt.decode(
                token, 
                _get_jwt_secret(), 
                algorithms=[_get_jwt_algorithm()]
            )
        except jwt.ExpiredSignatureError as exc:
            self.logger.warning("Verification failed: Token expired")
            # Frontend treatment: Display "Link Expired" and prompt them to log in to request a new one
            raise NotAuthorizedException(
                title="Token Expired",
                description="This verification link has expired. Please log in to request a new one."
            ) from exc
        except jwt.InvalidTokenError as exc:
            self.logger.warning("Verification failed: Invalid token structure or signature")
            # Frontend treatment: Display "Invalid Link" error
            raise NotAuthorizedException(
                title="Invalid Token",
                description="This verification link is invalid or malformed."
            ) from exc

        # 2. Check the specific token type to prevent using Auth tokens here
        if payload.get("type") != "verify_email":
            self.logger.warning("Verification failed: Incorrect token type used")
            raise NotAuthorizedException(
                title="Invalid Token",
                description="Invalid token type provided."
            )

        # 3. Retrieve the User
        user_key_str = payload.get("sub")
        if not user_key_str:
            self.logger.warning("Verification failed: Token missing subject (sub)")
            raise NotAuthorizedException(
                title="Invalid Token",
                description="Token payload is malformed."
            )

        user = self.session.query(User).filter(User.user_key == user_key_str).first()
        if not user:
            self.logger.warning("Verification failed: User %s not found in DB", user_key_str)
            raise NotAuthorizedException(
                title="User Not Found",
                description="The account associated with this link no longer exists."
            )

        # 4. Idempotency Check (If they click the link twice)
        if getattr(user, "is_verified", False):
            self.logger.info("User %s is already verified. Ignoring duplicate request.", user.user_key)
            # Frontend treatment: Display Success (they are already verified, no need to show an error)
            return {"status": "success", "message": "Email is already verified."}

        # 5. Apply the Update
        user.is_verified = True
        try:
            self.session.commit()
            self.logger.info("User %s verified successfully", user.user_key)
        except Exception as exc:
            self.session.rollback()
            self.logger.exception("Database error while verifying user %s", user.user_key)
            raise ServiceUnavailableException(
                title="Database Error",
                description="Could not complete verification at this time. Please try again later."
            ) from exc

        # Frontend treatment: Display Success green checkmark
        return {"status": "success", "message": "Email verified successfully."}


    def resend_link(self, user: User) -> dict:
        """
        Generates and sends a fresh magic link. 
        Requires the user to be logged in (auth context).
        """
        self.logger.info("Attempting to resend verification link for user %s", user.user_key)

        # 1. Check if they actually need it
        if getattr(user, "is_verified", False):
            self.logger.warning("Resend failed: User %s is already verified", user.user_key)
            # Frontend treatment: Refresh the app state, route them to dashboard immediately
            raise ConflictException(
                title="Already Verified",
                description="Your account is already verified."
            )

        # 2. Generate new token
        verification_token = create_verification_token(user.user_key)
        
        # 3. Construct Link
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        magic_link = f"{frontend_url}/verify?token={verification_token}"
        
        # 4. Send Email
        email_sent = send_verification_email(user.email, user.username, magic_link)
        
        if not email_sent:
            self.logger.error("Resend failed: Email provider rejected the request for %s", user.email)
            # Frontend treatment: Show a toast saying "Failed to send email. Try again in a minute."
            raise ServiceUnavailableException(
                title="Email Delivery Failed",
                description="We could not send the email at this time. Please try again later."
            )
            
        self.logger.info("Verification email resent successfully to %s", user.email)
        
        # Frontend treatment: Show a toast saying "Email sent!" and start a 60-second cooldown timer on the button
        return {"status": "success", "message": "Verification link sent to your email."}