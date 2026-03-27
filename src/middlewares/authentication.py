import os
import logging
import stripe
from stripe import SignatureVerificationError
from uuid import UUID

import jwt
from sqlalchemy.orm import Session

from exception import NotAuthorizedException, ServiceUnavailableException, ForbiddenException, BadRequestException
from models.user import User

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    def process_resource(self, req, resp, resource, params):
        if resource is not None and getattr(resource, "auth_required", True) is False:
            return

        # Public Endpoints
        path = getattr(req, "path", "") or ""
        if path == "/health":
            return

        # Stripe webhooks (authenticated via Stripe signature)
        if self._is_stripe_webhook_path(path):
            payload = req.bounded_stream.read()
            sig_header = req.get_header("Stripe-Signature")
            event = self._verify_stripe_signature(payload, sig_header)
            req.context.stripe_event = event
            return

        # Protected Admin endpoints
        is_admin_resource = getattr(resource, "admin_required", False)
        if is_admin_resource:
            expected_secret = os.environ.get("ADMIN_SECRET_KEY", "").strip()
            if not expected_secret:
                raise ServiceUnavailableException(
                    title="Service Unavailable",
                    description="Admin secret key is not configured on the server."
                )

            provided_token = req.get_header("X-Admin-Token")
            
            if not provided_token or provided_token != expected_secret:
                raise ForbiddenException(
                    title="Forbidden",
                    description="Missing or invalid Authorization header."
                )
            
            return


        # Protected User endpoints
        auth_header = req.get_header("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Missing or invalid Authorization header. Use Bearer <token>.",
            )

        token = auth_header[7:].strip()
        if not token:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Missing or invalid Authorization header. Use Bearer <token>.",
            )

        secret = os.environ.get("JWT_SECRET", "").strip()
        if not secret:
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="JWT secret is not configured.",
            )

        algorithm = os.environ.get("JWT_ALGORITHM", "HS256").strip() or "HS256"
        try:
            payload = jwt.decode(token, secret, algorithms=[algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Token has expired.",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Invalid token.",
            ) from exc

        subject = payload.get("sub")
        if not subject:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Invalid token subject.",
            )

        try:
            user_key = UUID(str(subject))
        except (TypeError, ValueError) as exc:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Invalid token subject.",
            ) from exc

        session: Session | None = getattr(req.context, "db_session", None)
        if session is None:
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Database session is not available.",
            )

        user = session.query(User).filter(User.user_key == user_key).first()
        if not user:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="User not found.",
            )

        req.context.user = user
        req.context.user_id = str(user.user_key)

    def _is_stripe_webhook_path(self, path: str) -> bool:
        return path in ("/app/stripe/webhooks", "app/stripe/webhooks")

    def _verify_stripe_signature(self, payload: bytes, sig_header: str | None):
        if not sig_header:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Missing Stripe-Signature header.",
            )

        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
        if not secret:
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Stripe webhook secret is not configured.",
            )

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, secret
            )
            return event
            
        except ValueError:
            raise BadRequestException(
                title="Bad Request",
                description="Invalid payload.",
            )
        except SignatureVerificationError:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Invalid Stripe signature or webhook is too old.",
            )
