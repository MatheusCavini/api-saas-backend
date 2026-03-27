import logging
import os
import json
from datetime import datetime, timezone
from uuid import UUID
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

        # 4. Check user membership inside workspace -> if not Owner, 403 Forbidden.
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
        success_url = os.environ.get("STRIPE_SUCCESS_URL", "").strip()
        cancel_url = os.environ.get("STRIPE_CANCEL_URL", "").strip()
        
        if not success_url or not cancel_url:
            self.logger.error("Stripe success/cancel URLs are not configured.")
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Stripe checkout is currently unavailable.",
            )

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                customer_email=user.email,
                client_reference_id=str(workspace_id),
                metadata={
                    "workspace_id": str(workspace_id),
                    "plan_id": str(plan.id), # Pass your internal plan ID, it's safer
                },
                line_items=[
                    {
                        "price": plan.stripe_price_id,
                        "quantity": 1,
                    }
                ],
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except Exception as exc:
            self.logger.exception("Stripe checkout session creation failed.")
            raise ServiceUnavailableException(
                title="Service Unavailable",
                description="Unable to create Stripe checkout session.",
            ) from exc
        
        return session.url


    def handle_webhook(self, event):
        if event.type != "checkout.session.completed":
            return {"status": "ignored"}
        
        session = event.data.object
        
        metadata = session.get("metadata", {})
      
        workspace_id_str = metadata.get("workspace_id") or session.get("client_reference_id")
        plan_id_str = metadata.get("plan_id") 
        stripe_customer_id = session.get("customer")
        stripe_sub_id = session.get("subscription")

        if not workspace_id_str or not plan_id_str or not stripe_customer_id or not stripe_sub_id:
            self.logger.critical("Stripe session missing required identifiers. Session ID: %s", session.get("id"))
            # Return 200 OK to Stripe so they don't retry, but log it internally.
            return {"status": "error", "message": "Missing required identifiers."}
        
        try:
            # Parse UUID instead of int
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
            # We must fetch the subscription to get the end date
            stripe_subscription = stripe.Subscription.retrieve(stripe_sub_id)
        except Exception as exc:
            self.logger.exception("Stripe subscription retrieval failed for %s", stripe_sub_id)
            return {"status": "error", "message": "Unable to retrieve subscription."}
        
        # Update the workspace with the newly minted customer ID
        workspace.stripe_customer_id = stripe_customer_id
        
        # Ensure the subscription actually has an item attached
        if not stripe_subscription["items"].data:
            self.logger.critical("Stripe subscription has no items for %s", stripe_sub_id)
            return {"status": "error", "message": "Subscription missing items."}

        # Fetch the end date from the first subscription item
        current_period_end_ts = stripe_subscription["items"].data[0].current_period_end
        
        if not current_period_end_ts:
            self.logger.critical("Stripe subscription item missing current_period_end for %s", stripe_sub_id)
            return {"status": "error", "message": "Subscription missing end date."}

        current_period_end = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)

        # Upsert Subscription logic
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
