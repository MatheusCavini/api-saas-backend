"""
CORS middleware. Sets Access-Control-Allow-* headers on all responses.
Short-circuits OPTIONS preflight with HTTP 200 so the request never reaches
rate limiter, auth, or resources.
"""
import falcon


ALLOW_ORIGIN = "*"
ALLOW_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
ALLOW_HEADERS = "Content-Type, Authorization"


class CorsMiddleware:
    def process_request(self, req, resp):
        if req.method == "OPTIONS":
            resp.status = falcon.HTTP_200
            resp.text = ""
            self._set_cors_headers(resp)
            resp.complete = True
            return

    def process_response(self, req, resp, resource, req_succeeded):
        self._set_cors_headers(resp)

    @staticmethod
    def _set_cors_headers(resp):
        resp.set_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        resp.set_header("Access-Control-Allow-Methods", ALLOW_METHODS)
        resp.set_header("Access-Control-Allow-Headers", ALLOW_HEADERS)
