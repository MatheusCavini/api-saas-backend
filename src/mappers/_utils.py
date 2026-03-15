"""Shared mapper helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID


def serialize_dt(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def serialize_uuid(value: UUID | None) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def related_key(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    for attr in dir(obj):
        if attr.endswith('_key'):
            return serialize_uuid(getattr(obj, attr, None))
    return None
