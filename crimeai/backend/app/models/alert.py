"""Alert ORM model for real-time notification system."""
from __future__ import annotations

import uuid
from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # hotspot | cluster | high_risk | pattern | system
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", index=True
    )  # low | medium | high | critical
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Geographic context
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Reference to triggering entity
    related_crime_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    related_cluster_id: Mapped[int | None] = mapped_column(nullable=True)

    # Target audience
    target_role: Mapped[str | None] = mapped_column(String(20), nullable=True)  # None = broadcast
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
