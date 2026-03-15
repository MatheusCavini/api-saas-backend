"""Map Role ORM models to API representations."""
from typing import Any

from mappers._utils import serialize_dt, serialize_uuid
from models.role import Role


def model_to_response(model: Role) -> dict[str, Any]:
    return {
        "role_key": serialize_uuid(model.role_key),
        "name": model.name,
        "description": model.description,
        "created_at": serialize_dt(model.created_at),
    }
