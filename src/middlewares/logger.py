import logging
import time
import uuid

class Logger():
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("api.access")

    def _ctx_set(self, req, key, value):
        try:
            req.context[key] = value
        except Exception:
            setattr(req.context, key, value)

    def _ctx_get(self, req, key, default=None):
        try:
            return req.context.get(key, default)
        except Exception:
            return getattr(req.context, key, default)

    def process_request(self, req, resp):
        request_id = self._ctx_get(req, "request_id")
        if not request_id:
            request_id = uuid.uuid4().hex
            self._ctx_set(req, "request_id", request_id)

        self._ctx_set(req, "_start_time", time.monotonic())

        self.logger.info(
            "REQ_IN | method=%-7s | path=%s | ip=%s",
            getattr(req, "method", "UNKNOWN"),
            getattr(req, "relative_uri", None) or getattr(req, "path", "UNKNOWN"),
            getattr(req, "remote_addr", "UNKNOWN"),
        )

    def process_response(self, req, resp, resource, req_succeeded):
        request_id = self._ctx_get(req, "request_id")
        start_time = self._ctx_get(req, "_start_time")
        duration_ms = None
        if start_time is not None:
            duration_ms = (time.monotonic() - start_time) * 1000.0

        self.logger.info(
            "REQ_OUT | status=%-7s | duration=%.2fms",
            getattr(resp, "status", "UNKNOWN"),
            duration_ms if duration_ms is not None else -1.0,
        )