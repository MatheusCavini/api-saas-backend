import os
import logging
from exception import NotAuthorizedException

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    def process_request(self, req, resp):
        path = getattr(req, "path", "") or ""

        if path == "/health":
            return

        if not path.startswith("/api/v1/"):
            return

        auth_header = req.get_header("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Missing or invalid Authorization header. Use Bearer <token>.",
            )

        token = auth_header[7:].strip()
        expected = os.environ.get("AUTH_BEARER_TOKEN", "").strip()
        if not expected or token != expected:
            raise NotAuthorizedException(
                title="Unauthorized",
                description="Invalid token.",
            )

        # Optional: set user identity for rate limiter / resources
        try:
            req.context["user_id"] = token[:16]
        except Exception:
            setattr(req.context, "user_id", token[:16])
