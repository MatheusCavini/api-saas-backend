"""Map Plan ORM models to API representations."""
from typing import Any

from mappers._utils import serialize_dt, serialize_uuid
from models.plan import Plan


def model_to_response(model: Plan) -> dict[str, Any]:
    return {
        "plan_key": serialize_uuid(model.plan_key),
        "stripe_price_id": model.stripe_price_id,
        "name": model.name,
        "monthly_quota": model.monthly_quota,
        "is_active": model.is_active,
        "created_at": serialize_dt(model.created_at),
    }
