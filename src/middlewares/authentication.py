import os
import logging
from uuid import UUID

import jwt
from sqlalchemy.orm import Session

from exception import NotAuthorizedException, ServiceUnavailableException, ForbiddenException
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
