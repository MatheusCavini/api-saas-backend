import falcon
import logging
import sys


from middlewares.cors import CorsMiddleware
from middlewares.db_session import SQLAlchemySessionManager
from middlewares.rate_limiter import RateLimiterMiddleware
from middlewares.authentication import AuthenticationMiddleware
from middlewares.logger import Logger

from database.db import SessionLocal
from utils.bracket_formatter import BracketFormatter
from exception import ClientException, handle_client_error, handle_unexpected_error
import models


from resources.health_check import HealthCheckResource
from resources.auth_resource import AuthResource
from resources.workspace import WorkspaceResource
from resources.user import UserResource
from resources.admin.plan import AdminPlanResource
from resources.plan import PlanResource
from resources.stripe import StripeResource



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
    api.add_route("/auth/register", auth_resource, suffix="register")
    api.add_route("/auth/login", auth_resource, suffix="login")
    api.add_route("/auth/oauth/google", auth_resource, suffix="oauth_google")

    workspace_resource = WorkspaceResource()
    api.add_route("/app/workspace", workspace_resource)

    admin_plan_resource = AdminPlanResource()
    api.add_route("/admin/plan", admin_plan_resource)

    plan_resource = PlanResource()
    api.add_route("/app/plan", plan_resource)

    stripe_resource = StripeResource()
    api.add_route("/app/stripe/select", stripe_resource, suffix="plan_selection")
    api.add_route("/app/stripe/webhooks", stripe_resource, suffix="webhook")



    user_resource = UserResource()
    api.add_route("/app/user/me", user_resource)


    api.add_error_handler(ClientException, handle_client_error)
    api.add_error_handler(Exception, handle_unexpected_error)

    log.info("Falcon API initialized")
    return api


api = create()
