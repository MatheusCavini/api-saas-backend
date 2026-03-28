"""Falcon resource for PlanController operations."""
import falcon
import logging
import stripe
import os
from controllers.stripe import StripeController
from exception import BadRequestException
from utils.validator import validate_payload


class StripeResource:

    auth_required = True
    admin_required = False

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

        if not stripe.api_key:
            # It's good practice to crash early if this is missing so you don't find out in production!
            raise RuntimeError("STRIPE_SECRET_KEY environment variable is not set.")

    def on_post_plan_selection(self, req, resp):
        stripe_controller = StripeController(req.context.db_session)
        self.logger.info("Processing POST request for plan selection")
        payload = req.media or {}
        validate_payload(payload, "plan_selection")
        checkout_url = stripe_controller.create_checkout_session(payload, req.context.user)
        resp.status = falcon.HTTP_200
        resp.media = {"url": checkout_url}

    def on_post_customer_portal(self, req, resp):
        stripe_controller = StripeController(req.context.db_session)
        self.logger.info("Processing POST request for Stripe customer portal")
        payload = req.media or {}
        checkout_url = stripe_controller.create_customer_portal(req.context.user, payload)
        resp.status = falcon.HTTP_200
        resp.media = {"url": checkout_url}

    def on_post_webhook(self, req, resp):
        stripe_controller = StripeController(req.context.db_session)
        self.logger.info("Processing Stripe Webhook")
        resp.media = stripe_controller.handle_webhook(req.context.stripe_event)
        resp.status = falcon.HTTP_200



