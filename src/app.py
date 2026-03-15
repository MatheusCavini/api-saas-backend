import falcon
import logging
import sys

from utils.bracket_formatter import BracketFormatter
from middlewares.cors import CorsMiddleware
from middlewares.db_session import SQLAlchemySessionManager
from middlewares.rate_limiter import RateLimiterMiddleware
from middlewares.authentication import AuthenticationMiddleware
from middlewares.logger import Logger
from database.db import SessionLocal
from resources.health_check import HealthCheckResource
from resources.sample_entity import SampleEntityResource
from exception import ClientException, handle_client_error, handle_unexpected_error


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

    api.add_route("/health", HealthCheckResource())
    api.add_route("/api/v1/sample_entities", SampleEntityResource())
    api.add_route("/api/v1/sample_entities/{entity_id}", SampleEntityResource())

    api.add_error_handler(ClientException, handle_client_error)
    api.add_error_handler(Exception, handle_unexpected_error)

    log.info("Falcon API initialized")
    return api


api = create()
