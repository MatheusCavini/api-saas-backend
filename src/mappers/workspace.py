"""Map Workspace ORM models to API representations."""
from typing import Any

from mappers._utils import serialize_dt, serialize_uuid
from models.workspace import Workspace


def model_to_response(model: Workspace) -> dict[str, Any]:
    return {
        "workspace_key": serialize_uuid(model.workspace_key),
        "name": model.name,
        "stripe_customer_id": model.stripe_customer_id,
        "created_at": serialize_dt(model.created_at),
    }
