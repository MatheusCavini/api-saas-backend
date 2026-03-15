"""Falcon resource for authentication endpoints."""
from __future__ import annotations

import falcon
import logging

from controllers.auth import google_oauth_login, login_user, register_user
from utils.validator import validate_payload


class AuthResource:
    auth_required = False

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_post_register(self, req, resp):
        self.logger.info("Processing POST request for auth register")
        payload = req.media or {}
        validate_payload(payload, "auth_register")
        result = register_user(req.context.db_session, payload)
        resp.media = result
        resp.status = falcon.HTTP_201

    def on_post_login(self, req, resp):
        self.logger.info("Processing POST request for auth login")
        payload = req.media or {}
        validate_payload(payload, "auth_login")
        result = login_user(req.context.db_session, payload)
        resp.media = result
        resp.status = falcon.HTTP_200

    def on_post_oauth_google(self, req, resp):
        self.logger.info("Processing POST request for auth Google OAuth")
        payload = req.media or {}
        validate_payload(payload, "auth_oauth_google")
        result = google_oauth_login(req.context.db_session, payload)
        resp.media = result
        resp.status = falcon.HTTP_200
