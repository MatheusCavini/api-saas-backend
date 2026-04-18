import logging
import os
import json
from datetime import datetime, timedelta, timezone
import stripe

from sqlalchemy.exc import IntegrityError

from exception import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotAuthorizedException,
    NotFoundException,
    ServiceUnavailableException,
)
from mappers.workspace import model_to_response as workspace_to_response
from models import usage
from models.plan import Plan
from models.role import Role
from models.subscription import Subscription
from models.workspace import Workspace
from models.workspace_member import WorkspaceMember


class StripeController():
    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)

    def create_checkout_session(self, payload: dict, user):
        locale = payload.get("locale")
        if locale == 'pt':
            locale = "pt-BR"
        self.logger.info(f"Locale is set to {locale}")
        stripe_locale = locale if locale in ["en", "pt-BR", "es"] else "auto"
        
        # 1. Extract plan_id and workspace_id from the payload.
        plan_key = payload.get("plan_key")

        # 2. Check if the Plan exists in DB -> if not, 404 NotFound.
        try: 
            plan = (
                self.db_session.query(Plan)
                .filter(Plan.is_active.is_(True))
                .filter(Plan.plan_key == plan_key)
                .order_by(Plan.created_at.desc())
                .one()
            )
        except:
            raise NotFoundException(
                title="Not Found",
                description="Plan not found.",
            )

        if not plan:
            self.logger.warning("Plan not found for plan_key=%s", plan_key)
            raise NotFoundException(
                title="Not Found",
                description="Plan not found.",
            )

        # 3. Check user membership inside workspace -> if not Owner, 403 Forbidden.
        membership = self._get_membership_for_user(user)

        if membership.role.name != "owner":
            self.logger.warning(
                "Plan subscription forbidden for user_id=%s on workspace_id=%s",
                user.id,
                membership.workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="Only workspace owners can subscribe to plans.",
            )

        workspace_id = membership.workspace_id
        
        # Fetch the workspace to check for an existing stripe_customer_id
        workspace = self.db_session.query(Workspace).filter(Workspace.id == workspace_id).first()
        
        success_url = os.environ.get("STRIPE_SUCCESS_URL", "").strip()
        cancel_url = os.environ.get("STRIPE_CANCEL_URL", "").strip()
        
        if not success_url or not cancel_url:
            self.logger.error("Stripe success/cancel URLs are not configured.")
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Stripe checkout is currently unavailable.",
            )

        # 4. Handle Free Plan Locally
        if plan.stripe_price_id == "FREE":
            self.logger.info("Free plan selected. Bypassing Stripe and handling locally.")
            self._apply_free_plan(workspace_id, plan.id)
            return success_url

        # 5. Build Checkout Session parameters
        session_kwargs = {
            "mode": "subscription",
            "locale": stripe_locale,
            "client_reference_id": str(workspace_id),
            "metadata": {
                "workspace_id": str(workspace_id),
                "plan_id": str(plan.id),
            },
            "line_items": [
                {
                    "price": plan.stripe_price_id,
                    "quantity": 1,
                }
            ],
            "success_url": success_url,
            "cancel_url": cancel_url,
        }

        # Prevent duplicate Stripe customers if they previously paid and downgraded
        if workspace and not workspace.stripe_customer_id:
            session_kwargs["customer"] = workspace.stripe_customer_id
        else:
            session_kwargs["customer_email"] = user.email

        # 6. Create the Session
        try:
            session = stripe.checkout.Session.create(**session_kwargs)
        except Exception as exc:
            self.logger.exception("Stripe checkout session creation failed.")
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Unable to create Stripe checkout session.",
            ) from exc
        
        return session.url

    def create_customer_portal(self, user, payload:dict):
        locale = payload.get("locale")
        if locale == 'pt':
            locale = "pt-BR"
        self.logger.info(f"Locale is set to {locale}")
        stripe_locale = locale if locale in ["en", "pt-BR", "es"] else "auto"

        # 1. Check user membership inside workspace -> if not Owner, 403 Forbidden.
        membership = self._get_membership_for_user(user)

        if membership.role.name != "owner":
            self.logger.warning(
                "Customer portal access forbidden for user_id=%s on workspace_id=%s",
                user.id,
                membership.workspace_id,
            )
            raise ForbiddenException(
                title="Forbidden",
                description="Only workspace owners can manage billing.",
            )

        workspace_id = membership.workspace_id

        # 2. Retrieve the workspace to get the Stripe Customer ID
        workspace = (
            self.db_session.query(Workspace)
            .filter(Workspace.id == workspace_id)
            .first()
        )

        # If they don't have a stripe_customer_id, they haven't checked out yet
        # 3. Handle Free Users (No Stripe Customer ID)
        # Instead of a Bad Request, redirect them to the frontend plan selection page.
        if not workspace or not workspace.stripe_customer_id:
            self.logger.info(
                "Stripe customer ID not found for workspace_id=%s. Redirecting to plan selection.", 
                workspace_id
            )
            # Make sure to add this environment variable to your .env file!
            upgrade_url = "http://localhost:3000/onboarding"
            
            if not upgrade_url:
                self.logger.error("FRONTEND_PLAN_SELECTION_URL is not configured.")
                raise ServiceUnavailableException(
                    title="Service Unavailable",
                    description="Plan selection routing is currently unavailable.",
                )
            
            return upgrade_url

        # 3. Get the return URL (where the user goes when they click "Return to App" in Stripe)
        return_url = os.environ.get("STRIPE_RETURN_URL", "").strip()
        
        if not return_url:
            self.logger.error("Stripe portal return URL is not configured.")
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Billing portal is currently unavailable.",
            )

        # 4. Create the Portal Session
        try:
            session = stripe.billing_portal.Session.create(
                customer=workspace.stripe_customer_id,
                return_url=return_url,
                locale=stripe_locale
            )
        except Exception as exc:
            self.logger.exception("Stripe customer portal session creation failed.")
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Unable to create Stripe billing portal session.",
            ) from exc
        
        return session.url


    def handle_webhook(self, event):
        event_type = event.type
        event_object = event.data.object

        # 1. Map Stripe event types to your specific handler functions
        handlers = {
            "checkout.session.completed": self._handle_checkout_completed,
            "checkout.session.async_payment_succeeded": self._handle_checkout_completed,
            "customer.subscription.updated": self._handle_subscription_updated,
            "customer.subscription.deleted": self._handle_subscription_deleted,
        }

        # 2. Get the right function for the event
        handler_func = handlers.get(event_type)

        # 3. Execute the function if it exists, otherwise ignore gracefully
        if handler_func:
            self.logger.info("Dispatching Stripe webhook: %s", event_type)
            try:
                return handler_func(event_object)
            except Exception as exc:
                self.logger.exception("Error processing webhook %s", event_type)
                return {"status": "error", "message": "Internal processing error."}
        else:
            self.logger.debug("Ignored unhandled Stripe event: %s", event_type)
            return {"status": "ignored"}


    # ---------------------------------------------------------
    # Private Webhook Handlers
    # ---------------------------------------------------------

    def _handle_checkout_completed(self, session):
        payment_status = getattr(session, "payment_status", None)
        if payment_status != "paid" and payment_status != "no_payment_required": 
            self.logger.warning("Checkout completed but payment status is %s for session %s", payment_status, session.id)
            return {"status": "ignored", "message": "Payment not completed yet."}

        metadata = getattr(session, "metadata", {}) or {}
        
        workspace_id_str = metadata.get("workspace_id") or getattr(session, "client_reference_id", None)
        plan_id_str = metadata.get("plan_id")
        stripe_customer_id = getattr(session, "customer", None)
        stripe_sub_id = getattr(session, "subscription", None)

        if not workspace_id_str or not plan_id_str or not stripe_customer_id or not stripe_sub_id:
            self.logger.critical("Stripe session missing required identifiers. Session ID: %s", getattr(session, "id", "Unknown"))
            return {"status": "error", "message": "Missing required identifiers."}

        # FIX: Moved Idempotency check UP to avoid unnecessary Stripe API calls on duplicates
        existing_sub = self.db_session.query(Subscription).filter(Subscription.stripe_sub_id == stripe_sub_id).first()
        if existing_sub:
            self.logger.info("Webhook already processed for subscription %s. Ignoring duplicate.", stripe_sub_id)
            return {"status": "success"} 
        
        try:
            workspace_id = int(workspace_id_str)
            plan_id = int(plan_id_str)
        except (TypeError, ValueError):
            self.logger.critical("Invalid identifiers in Stripe session metadata.")
            return {"status": "error", "message": "Invalid ID format."}

        workspace = self.db_session.query(Workspace).filter(Workspace.id == workspace_id).first()
        plan = self.db_session.query(Plan).filter(Plan.id == plan_id).first()
        
        if not workspace or not plan:
            self.logger.critical("Workspace or Plan not found for webhook. workspace_id=%s, plan_id=%s", workspace_id, plan_id)
            return {"status": "error", "message": "Record not found."}
        
        try:
            stripe_subscription = stripe.Subscription.retrieve(stripe_sub_id)
        except Exception as exc:
            self.logger.exception("Stripe subscription retrieval failed for %s", stripe_sub_id)
            return {"status": "error", "message": "Unable to retrieve subscription."}
        
        workspace.stripe_customer_id = stripe_customer_id
        
        if not stripe_subscription["items"].data:
            self.logger.critical("Stripe subscription has no items for %s", stripe_sub_id)
            return {"status": "error", "message": "Subscription missing items."}

        current_period_end_ts = stripe_subscription["items"].data[0].current_period_end
        if not current_period_end_ts:
            self.logger.critical("Stripe subscription item missing current_period_end for %s", stripe_sub_id)
            return {"status": "error", "message": "Subscription missing end date."}

        current_period_end = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)

        subscription = (
            self.db_session.query(Subscription)
            .filter(Subscription.workspace_id == workspace.id)
            .filter(Subscription.status == "active")
            .order_by(Subscription.created_at.desc())
            .first()
        )
        
        if subscription:
            self.logger.info("Updating existing subscription for workspace_id=%s", workspace.id)
            subscription.plan_id = plan.id
            subscription.stripe_sub_id = stripe_sub_id
            subscription.status = "active"
            subscription.current_period_end = current_period_end
        else:
            self.logger.info("Creating new subscription for workspace_id=%s", workspace.id)
            subscription = Subscription(
                workspace_id=workspace.id,
                plan_id=plan.id,
                stripe_sub_id=stripe_sub_id,
                status="active",
                current_period_end=current_period_end,
            )
            self.db_session.add(subscription)
        
        try:
            self.db_session.commit()
            self.logger.info("Successfully processed checkout for workspace_id=%s", workspace.id)
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Failed to persist subscription for workspace_id=%s", workspace.id)
            return {"status": "error", "message": "Database error."}
        
        return {"status": "success"}


    def _handle_subscription_updated(self, stripe_subscription):
        stripe_sub_id = getattr(stripe_subscription, "id", None)
        
        subscription = self.db_session.query(Subscription).filter(Subscription.stripe_sub_id == stripe_sub_id).first()
        if not subscription:
            self.logger.warning("Subscription %s not found in DB during update event.", stripe_sub_id)
            return {"status": "ignored"}

        # 1. Update the period end date
        current_period_end_ts = getattr(stripe_subscription, "current_period_end", None)
        if current_period_end_ts:
            subscription.current_period_end = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)

        # 2. FIX: Handle Plan Upgrades/Downgrades!
        # Extract the Stripe Price ID from the updated subscription payload
        items = stripe_subscription.get("items") # <--- USE .get() INSTEAD
        if items and items.data:
            stripe_price_id = items.data[0].price.id
            
            # Find the corresponding Plan in your DB by its Stripe Price ID
            new_plan = self.db_session.query(Plan).filter(Plan.stripe_price_id == stripe_price_id).first()
            if new_plan and subscription.plan_id != new_plan.id:
                self.logger.info("Subscription %s changed to new plan: %s", stripe_sub_id, new_plan.name)
                subscription.plan_id = new_plan.id

        # 3. Sync the actual status
        stripe_status = getattr(stripe_subscription, "status", "unknown")
        
        if stripe_status in ["past_due", "unpaid", "incomplete", "incomplete_expired"]:
            self.logger.warning("Subscription %s is %s. Revoking active status.", stripe_sub_id, stripe_status)
            subscription.status = "payment_failed" 
        elif stripe_status in ["active", "trialing"]: # Added trialing just in case you ever use Free Trials!
            subscription.status = "active"
        elif stripe_status == "canceled":
            subscription.status = "canceled"

        self.db_session.commit()
        self.logger.info("Updated subscription %s (Status: %s) from Stripe event.", stripe_sub_id, stripe_status)
        return {"status": "success"}

    def _handle_subscription_deleted(self, stripe_subscription):
        stripe_sub_id = getattr(stripe_subscription, "id", None)
        
        subscription = self.db_session.query(Subscription).filter(Subscription.stripe_sub_id == stripe_sub_id).first()
        if not subscription:
            self.logger.warning("Subscription %s not found in DB during delete event.", stripe_sub_id)
            return {"status": "ignored"}

        subscription.status = "canceled"
        self.db_session.commit()
        
        self.logger.info("Subscription %s period ended and was marked as canceled.", stripe_sub_id)
        return {"status": "success"}


    def _get_membership_for_user(self, user, workspace_key: str | None = None) -> WorkspaceMember:
        query = (
            self.db_session.query(WorkspaceMember)
            .join(Workspace)
            .filter(WorkspaceMember.user_id == user.id)
            .filter(Workspace.deactivated_on.is_(None))
        )

        if workspace_key:
            try:
                workspace_uuid = UUID(str(workspace_key))
            except (TypeError, ValueError) as exc:
                self.logger.warning("Invalid workspace_key=%s provided.", workspace_key)
                raise BadRequestException(
                    title="Bad Request",
                    description="Invalid workspace_key.",
                ) from exc
            query = query.filter(Workspace.workspace_key == workspace_uuid)

        memberships = query.all()
        if not memberships:
            self.logger.warning("Workspace membership not found for user_id=%s", user.id)
            raise NotFoundException(
                title="Not Found",
                description="Workspace not found.",
            )

        if not workspace_key and len(memberships) > 1:
            self.logger.warning(
                "Multiple workspaces found for user_id=%s; workspace_key required.",
                user.id,
            )
            raise BadRequestException(
                title="Bad Request",
                description="Multiple workspaces found. Provide workspace_key.",
            )

        return memberships[0]


    def cancel_workspace_subscription(self, workspace_id: int) -> None:
        """
        Immediately cancels every non-canceled Stripe subscription for a workspace.
        Called when a workspace is being deleted. Does not commit; the caller
        should commit the session together with other workspace teardown changes.
        """
        subscriptions = (
            self.db_session.query(Subscription)
            .filter(Subscription.workspace_id == workspace_id)
            .filter(Subscription.status != "canceled")
            .order_by(Subscription.created_at.desc())
            .all()
        )

        if not subscriptions:
            self.logger.info(
                "No cancellable Stripe subscriptions for workspace_id=%s", workspace_id
            )
            return


        for subscription in subscriptions:
            stripe_sub_id = subscription.stripe_sub_id
            try:
                stripe.Subscription.delete(stripe_sub_id)
                self.logger.info(
                    "Canceled Stripe subscription %s for workspace_id=%s",
                    stripe_sub_id,
                    workspace_id,
                )
            except stripe.error.InvalidRequestError as exc:
                if getattr(exc, "code", None) != "resource_missing":
                    self.logger.exception(
                        "Failed to cancel Stripe subscription %s for workspace_id=%s",
                        stripe_sub_id,
                        workspace_id,
                    )
                    raise ServiceUnavailableException(
                        title="Service Unavailable",
                        description="Unable to cancel the active subscription. Workspace deletion aborted.",
                    ) from exc
                self.logger.info(
                    "Stripe subscription %s already gone; marking canceled in DB.",
                    stripe_sub_id,
                )
            except Exception as exc:
                self.logger.exception(
                    "Failed to cancel Stripe subscription %s for workspace_id=%s",
                    stripe_sub_id,
                    workspace_id,
                )
                raise ServiceUnavailableException(
                    title="Service Unavailable",
                    description="Unable to cancel the active subscription. Workspace deletion aborted.",
                ) from exc

            subscription.status = "canceled"


    def _apply_free_plan(self, workspace_id: int, plan_id: int) -> None:
        """
        Creates a local-only subscription for the Free plan and marks any 
        other active subscriptions as canceled.
        """
        # Ensure any currently active subscriptions are marked as canceled locally
        existing_subs = (
            self.db_session.query(Subscription)
            .filter(Subscription.workspace_id == workspace_id)
            .filter(Subscription.status == "active")
            .all()
        )
        
        for sub in existing_subs:
            sub.status = "canceled"
            
        now = datetime.now(timezone.utc)
        one_month_from_now = now + timedelta(days=30)
        # Create the new free subscription (No Stripe ID, No Expiration)
        free_subscription = Subscription(
            workspace_id=workspace_id,
            plan_id=plan_id,
            stripe_sub_id="FREE_"+str(workspace_id),  # Key indicator of a free plan
            status="active",
            current_period_end=one_month_from_now  # Free plans don't expire
        )
        
        self.db_session.add(free_subscription)
        
        try:
            self.db_session.commit()
            self.logger.info("Successfully applied Free Plan for workspace_id=%s", workspace_id)
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Failed to persist Free Plan for workspace_id=%s", workspace_id)
            raise ServiceUnavailableException(
                title="Database Error",
                description="Unable to apply the free plan."
            ) from exc