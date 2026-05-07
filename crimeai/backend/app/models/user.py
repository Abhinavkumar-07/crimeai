"""User ORM model."""
from __future__ import annotations

import uuid
from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="police")
    badge_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships (defined as strings to avoid circular imports)
    fir_reports: Mapped[list] = relationship("FIRReport", back_populates="submitted_by_user", lazy="noload")
    audit_logs: Mapped[list] = relationship("AuditLog", back_populates="user", lazy="noload")
