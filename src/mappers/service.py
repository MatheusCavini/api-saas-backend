"""Map Service ORM models to API representations."""
from typing import Any

from mappers._utils import serialize_dt, serialize_uuid
from models.service import Service


def model_to_response(model: Service) -> dict[str, Any]:
    return {
        "service_key": serialize_uuid(model.service_key),
        "slug": model.slug,
        "name": model.name,
        "description": model.description,
        "credit_cost": model.credit_cost,
        "created_at": serialize_dt(model.created_at),
    }
