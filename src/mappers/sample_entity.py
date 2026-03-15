"""Map ORM models to/from API representations."""
from datetime import datetime
from typing import Any, Optional

from models.sample_entity import SampleEntity


def model_to_response(model: SampleEntity) -> dict[str, Any]:
    """Convert a SampleEntity model to API response dict."""
    return {
        "id": model.id,
        "name": model.name,
        "email": model.email,
        "description": model.description,
        "created_at": _serialize_dt(model.created_at),
        "updated_at": _serialize_dt(model.updated_at),
    }


def _serialize_dt(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)
