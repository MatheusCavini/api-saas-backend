"""Map ApiKey ORM models to API representations."""
from typing import Any

from mappers._utils import related_key, serialize_dt, serialize_uuid
from models.api_key import ApiKey


def model_to_response(model: ApiKey) -> dict[str, Any]:
    return {
        "api_key_key": serialize_uuid(model.api_key_key),
        "workspace_key": related_key(model.workspace),
        "name": model.name,
        "key_prefix": model.key_prefix,
        "status": model.status,
        "created_at": serialize_dt(model.created_at),
    }
