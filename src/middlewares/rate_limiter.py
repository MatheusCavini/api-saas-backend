"""
Rate limiting middleware using Redis. Limit 100 requests per minute per IP
(or per authenticated user id if available). Uses ConnectorSingleton.
"""
import falcon
import logging
from exception import TooManyRequestsException

from connectors.redis_connector import get_client

logger = logging.getLogger(__name__)

RATE_LIMIT_KEY_PREFIX = "rate_limit:"
RATE_LIMIT_MAX = 100
RATE_LIMIT_WINDOW_SEC = 60
SKIP_PATHS = ("/health",)


class RateLimiterMiddleware:
    def process_request(self, req, resp):
        path = getattr(req, "path", "") or ""
        if path.rstrip("/") in SKIP_PATHS:
            return

        identifier = self._get_identifier(req)
        key = f"{RATE_LIMIT_KEY_PREFIX}{identifier}"

        try:
            client = get_client()
            count = client.incr(key)
            if count == 1:
                client.expire(key, RATE_LIMIT_WINDOW_SEC)
            if count > RATE_LIMIT_MAX:
                logger.warning("Rate limit exceeded for key=%s count=%s", key, count)
                raise TooManyRequestsException(
                    title="Too Many Requests",
                    description=f"Rate limit exceeded: {RATE_LIMIT_MAX} requests per {RATE_LIMIT_WINDOW_SEC // 60} minute(s). Please try again later.",
                )
        except TooManyRequestsException:
            raise
        except Exception as e:
            logger.exception("Rate limiter Redis error: %s", e)
            # Allow request through if Redis fails (fail open)

    @staticmethod
    def _get_identifier(req) -> str:
        # Prefer authenticated user id if set by auth middleware
        try:
            uid = getattr(req.context, "user_id", None) or req.context.get("user_id")
            if uid:
                return str(uid)
        except Exception:
            pass
        # Fall back to IP (support X-Forwarded-For behind proxy)
        forwarded = req.get_header("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return getattr(req, "remote_addr", "unknown") or "unknown"
