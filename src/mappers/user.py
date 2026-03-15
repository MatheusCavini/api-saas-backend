"""Map User ORM models to API representations."""
from typing import Any

from mappers._utils import serialize_dt, serialize_uuid
from models.user import User


def model_to_response(model: User) -> dict[str, Any]:
    return {
        "user_key": serialize_uuid(model.user_key),
        "username": model.username,
        "email": model.email,
        "created_at": serialize_dt(model.created_at),
    }
