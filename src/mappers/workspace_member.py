"""Map WorkspaceMember ORM models to API representations."""
from typing import Any

from mappers._utils import related_key, serialize_dt
from models.workspace_member import WorkspaceMember


def model_to_response(model: WorkspaceMember) -> dict[str, Any]:
    return {
        "workspace_key": related_key(model.workspace),
        "user_key": related_key(model.user),
        "name": model.user.username if model.user else None,
        "email": model.user.email if model.user else None,
        "role": model.role.name if model.role else None,
        "role_key": related_key(model.role),
        "created_at": serialize_dt(model.created_at),
    }
