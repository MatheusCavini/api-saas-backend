"""Falcon resource for API key operations."""

import falcon
import logging

from controllers.api_key import ApiKeyController
from utils.validator import validate_payload


class ApiKeyResource:
    auth_required = True

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_post(self, req, resp):
        api_key_controller = ApiKeyController(req.context.db_session)
        self.logger.info("Processing POST request for api key creation")
        payload = req.media or {}
        validate_payload(payload, "api_key_create")
        resp.media = api_key_controller.create(payload, req.context.user)
        resp.status = falcon.HTTP_201

    def on_get(self, req, resp):
        # Optional alias: /app/api-key?api_key_key=...
        api_key_key = req.get_param("api_key_key")
        api_key_controller = ApiKeyController(req.context.db_session)
        if api_key_key:
            self.logger.info("Processing GET request for api key metadata (query param)")
            resp.media = api_key_controller.get_api_key(req.context.user, api_key_key)
        else:
            self.logger.info("Processing GET request for api key list")
            resp.media = api_key_controller.list_api_keys(req.context.user)
        resp.status = falcon.HTTP_200

    def on_get_by_key(self, req, resp, api_key_key):
        api_key_controller = ApiKeyController(req.context.db_session)
        self.logger.info("Processing GET request for api key metadata")
        resp.media = api_key_controller.get_api_key(req.context.user, api_key_key)
        resp.status = falcon.HTTP_200

    def on_delete_by_key(self, req, resp, api_key_key):
        api_key_controller = ApiKeyController(req.context.db_session)
        self.logger.info("Processing DELETE request for api key")
        api_key_controller.delete_api_key(req.context.user, api_key_key)
        resp.status = falcon.HTTP_204
