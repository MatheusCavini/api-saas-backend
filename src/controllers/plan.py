"""Business logic and DB operations for plans."""
import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from exception import BadRequestException, ConflictException, NotFoundException
from mappers.plan import model_to_response as plan_to_response
from models.plan import Plan


class PlanController:
    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)

    def create(self, payload: dict) -> dict:
        name = str(payload.get("name", "")).strip()
        stripe_price_id = str(payload.get("stripe_price_id", "")).strip()
        monthly_quota = payload.get("monthly_quota")

        if not name:
            raise BadRequestException(
                title="Bad Request",
                description="Plan name is required.",
            )
        if not stripe_price_id:
            raise BadRequestException(
                title="Bad Request",
                description="stripe_price_id is required.",
            )
        if monthly_quota is None:
            raise BadRequestException(
                title="Bad Request",
                description="monthly_quota is required.",
            )

        self.logger.info("Creating plan for stripe_price_id=%s", stripe_price_id)
        plan = Plan(
            name=name,
            stripe_price_id=stripe_price_id,
            monthly_quota=monthly_quota,
        )
        self.db_session.add(plan)
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Plan create failed due to integrity error.")
            raise ConflictException(
                title="Conflict",
                description="Plan with this stripe_price_id already exists.",
            ) from exc
        self.db_session.refresh(plan)
        self.logger.info("Plan created with plan_key=%s", plan.plan_key)
        return plan_to_response(plan)

    def list_active(self) -> list[dict]:
        plans = (
            self.db_session.query(Plan)
            .filter(Plan.is_active.is_(True))
            .order_by(Plan.created_at.desc())
            .all()
        )
        self.logger.info("Found %s active plans", len(plans))
        return [plan_to_response(plan) for plan in plans]

    def update(self, payload: dict, plan_key: str | None = None) -> dict:
        plan_key = plan_key or payload.get("plan_key")
        plan = self._get_plan_by_key(plan_key)

        updated = False

        if "name" in payload:
            name = str(payload.get("name", "")).strip()
            if not name:
                raise BadRequestException(
                    title="Bad Request",
                    description="Plan name cannot be empty.",
                )
            plan.name = name
            updated = True

        if "stripe_price_id" in payload:
            stripe_price_id = str(payload.get("stripe_price_id", "")).strip()
            if not stripe_price_id:
                raise BadRequestException(
                    title="Bad Request",
                    description="stripe_price_id cannot be empty.",
                )
            plan.stripe_price_id = stripe_price_id
            updated = True

        if "monthly_quota" in payload:
            monthly_quota = payload.get("monthly_quota")
            if monthly_quota is None:
                raise BadRequestException(
                    title="Bad Request",
                    description="monthly_quota cannot be empty.",
                )
            plan.monthly_quota = monthly_quota
            updated = True

        if not updated:
            raise BadRequestException(
                title="Bad Request",
                description="No fields provided to update.",
            )

        self.logger.info("Updating plan plan_key=%s", plan.plan_key)
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            self.logger.exception("Plan update failed due to integrity error.")
            raise ConflictException(
                title="Conflict",
                description="Plan could not be updated due to a conflict.",
            ) from exc
        self.db_session.refresh(plan)
        self.logger.info("Plan updated plan_key=%s", plan.plan_key)
        return plan_to_response(plan)

    def delete(self, plan_key: str | None) -> None:
        plan = self._get_plan_by_key(plan_key)
        if not plan.is_active:
            self.logger.info("Plan already inactive plan_key=%s", plan.plan_key)
            return

        self.logger.info("Deactivating plan plan_key=%s", plan.plan_key)
        plan.is_active = False
        self.db_session.commit()

    def _get_plan_by_key(self, plan_key: str | None) -> Plan:
        if not plan_key:
            raise BadRequestException(
                title="Bad Request",
                description="plan_key is required.",
            )

        try:
            plan_uuid = UUID(str(plan_key))
        except (TypeError, ValueError) as exc:
            self.logger.warning("Invalid plan_key=%s provided.", plan_key)
            raise BadRequestException(
                title="Bad Request",
                description="Invalid plan_key.",
            ) from exc

        plan = self.db_session.query(Plan).filter(Plan.plan_key == plan_uuid).first()
        if not plan:
            self.logger.warning("Plan not found for plan_key=%s", plan_key)
            raise NotFoundException(
                title="Not Found",
                description="Plan not found.",
            )
        return plan
