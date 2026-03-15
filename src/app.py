import falcon
import logging
import sys

from resources import auth_resource
from utils.bracket_formatter import BracketFormatter
from middlewares.cors import CorsMiddleware
from middlewares.db_session import SQLAlchemySessionManager
from middlewares.rate_limiter import RateLimiterMiddleware
from middlewares.authentication import AuthenticationMiddleware
from middlewares.logger import Logger
from database.db import SessionLocal
from resources.health_check import HealthCheckResource
from resources.sample_entity import SampleEntityResource
from resources.auth_resource import AuthResource
from exception import ClientException, handle_client_error, handle_unexpected_error
import models


def configure_logging():
    fmt = "%(process)-3s | %(asctime)s | %(level_bracket)-10s | %(name_bracket)-30s --- %(message)s"
    formatter = BracketFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        force=True 
    )


def create():
    configure_logging()
    log = logging.getLogger(__name__)

    api = falcon.App(
        middleware=[
            CorsMiddleware(),
            RateLimiterMiddleware(),
            AuthenticationMiddleware(),
            SQLAlchemySessionManager(SessionLocal),
            Logger(),
        ]
    )

    health_check_resource = HealthCheckResource()
    api.add_route("/health", health_check_resource)

    auth_resource = AuthResource()
    api.add_route("/api/v1/auth/register", auth_resource, suffix="register")
    api.add_route("/api/v1/auth/login", auth_resource, suffix="login")
    api.add_route("/api/v1/auth/oauth/google", auth_resource, suffix="oauth_google")

    sample_entity_resource = SampleEntityResource()
    api.add_route("/api/v1/sample_entities", sample_entity_resource)
    api.add_route("/api/v1/sample_entities/{entity_id}", sample_entity_resource)

    api.add_error_handler(ClientException, handle_client_error)
    api.add_error_handler(Exception, handle_unexpected_error)

    log.info("Falcon API initialized")
    return api


api = create()
