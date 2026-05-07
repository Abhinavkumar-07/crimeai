"""Crime ORM model with PostGIS geometry."""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Crime(Base):
    __tablename__ = "crimes"

    # Core fields
    crime_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sub_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 1-5

    # Location
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    # PostGIS geometry point (SRID 4326 = WGS84)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )

    # Temporal
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Investigation
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="reported", index=True
    )  # reported | under_investigation | resolved | closed
    case_number: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    assigned_officer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # ML fields (populated by ML service)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    fir_report: Mapped[object | None] = relationship("FIRReport", back_populates="crime", uselist=False)
