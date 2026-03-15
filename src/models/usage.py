"""Usage SQLAlchemy ORM model."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base


class Usage(Base):
    __tablename__ = "usage"
    __table_args__ = (
        Index("idx_usage_workspace_time", "workspace_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usage_key: Mapped[UUID] = mapped_column(
        "usage_key",
        PGUUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    credit_cost: Mapped[int] = mapped_column(Integer, nullable=False)

    workspace: Mapped["Workspace"] = relationship(back_populates="usage_events")
    api_key: Mapped["ApiKey | None"] = relationship(back_populates="usage_events")
    service: Mapped["Service"] = relationship(back_populates="usage_events")
