"""Map Usage ORM models to API representations."""
from typing import Any

from mappers._utils import related_key, serialize_dt, serialize_uuid
from models.usage import Usage


def model_to_response(model: Usage) -> dict[str, Any]:
    return {
        "usage_key": serialize_uuid(model.usage_key),
        "workspace_key": related_key(model.workspace),
        "api_key_key": related_key(model.api_key),
        "service_key": related_key(model.service),
        "timestamp": serialize_dt(model.timestamp),
        "status_code": model.status_code,
        "latency_ms": model.latency_ms,
        "credit_cost": model.credit_cost,
    }
