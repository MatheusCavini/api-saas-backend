"""
Custom exceptions and centralized Falcon error handlers.
All API errors return a consistent JSON shape:
{"error": "<code or title>", "message": "<human-readable>", "details": <optional>}.
"""
import logging
import falcon

logger = logging.getLogger(__name__)


class ClientException(Exception):
    def __init__(self, title: str, description: str, http_status: str, code: str | None = None, details=None):
        super().__init__(description)
        self.title = title
        self.description = description
        self.http_status = http_status
        self.code = code
        self.details = details

    def to_dict(self) -> dict:
        return {
            "error": self.code or self.title,
            "message": self.description,
            "details": self.details,
        }


class BadRequestException(ClientException):
    def __init__(self, title: str = "Bad Request", description: str = "The request was invalid.", code: str = "bad_request", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_400, code=code, details=details)


class NotAuthorizedException(ClientException):
    def __init__(self, title: str = "Unauthorized", description: str = "Authentication is required.", code: str = "unauthorized", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_401, code=code, details=details)


class ForbiddenException(ClientException):
    def __init__(self, title: str = "Forbidden", description: str = "You do not have permission to perform this action.", code: str = "forbidden", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_403, code=code, details=details)


class NotFoundException(ClientException):
    def __init__(self, title: str = "Not Found", description: str = "The requested resource was not found.", code: str = "not_found", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_404, code=code, details=details)


class MethodNotAllowedException(ClientException):
    def __init__(self, title: str = "Method Not Allowed", description: str = "The requested method is not allowed.", code: str = "method_not_allowed", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_405, code=code, details=details)


class ConflictException(ClientException):
    def __init__(self, title: str = "Conflict", description: str = "The request could not be completed due to a conflict.", code: str = "conflict", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_409, code=code, details=details)


class UnprocessableEntityException(ClientException):
    def __init__(self, title: str = "Unprocessable Entity", description: str = "The request was well-formed but could not be processed.", code: str = "unprocessable_entity", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_422, code=code, details=details)


class TooManyRequestsException(ClientException):
    def __init__(self, title: str = "Too Many Requests", description: str = "Too many requests. Please try again later.", code: str = "too_many_requests", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_429, code=code, details=details)


class ServiceUnavailableException(ClientException):
    def __init__(self, title: str = "Service Unavailable", description: str = "The service is temporarily unavailable.", code: str = "service_unavailable", details=None):
        super().__init__(title=title, description=description, http_status=falcon.HTTP_503, code=code, details=details)


def handle_client_error(req, resp, ex, params):
    """Handle ClientException and return consistent JSON body."""
    resp.status = ex.http_status
    resp.media = ex.to_dict()


def handle_unexpected_error(req, resp, ex, params):
    """Handle any uncaught Exception. Log and return 500 with generic message."""
    logger.exception("Unexpected error: %s", ex)
    resp.status = falcon.HTTP_500
    resp.media = {
        "error": "internal_server_error",
        "message": "There was an internal server error. Please try again later.",
    }
