"""Map Invitation ORM models to API representations."""
from typing import Any

from mappers._utils import related_key, serialize_dt, serialize_uuid
from models.invitation import Invitation


def model_to_response(model: Invitation) -> dict[str, Any]:
    return {
        "invitation_key": serialize_uuid(model.invitation_key),
        "workspace_key": related_key(model.workspace),
        "invited_email": model.invited_email,
        "host_user_key": related_key(model.host_user),
        "role_key": related_key(model.role),
        "status_key": related_key(model.status),
        "created_at": serialize_dt(model.created_at),
        "expires_at": serialize_dt(model.expires_at),
    }
