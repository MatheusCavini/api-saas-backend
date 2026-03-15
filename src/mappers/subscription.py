"""Map Subscription ORM models to API representations."""
from typing import Any

from mappers._utils import related_key, serialize_dt, serialize_uuid
from models.subscription import Subscription


def model_to_response(model: Subscription) -> dict[str, Any]:
    return {
        "subscription_key": serialize_uuid(model.subscription_key),
        "workspace_key": related_key(model.workspace),
        "plan_key": related_key(model.plan),
        "stripe_sub_id": model.stripe_sub_id,
        "status": model.status,
        "current_period_end": serialize_dt(model.current_period_end),
        "created_at": serialize_dt(model.created_at),
    }
