"""Workspace SQLAlchemy ORM model."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_key: Mapped[UUID] = mapped_column(
        "workspace_key",
        PGUUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid4,
        server_default=text("uuid_generate_v4()"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    deactivated_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    members: Mapped[list["WorkspaceMember"]] = relationship(back_populates="workspace")
    invitations: Mapped[list["Invitation"]] = relationship(back_populates="workspace")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="workspace")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="workspace")
    usage_events: Mapped[list["Usage"]] = relationship(back_populates="workspace")
