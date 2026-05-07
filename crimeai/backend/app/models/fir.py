"""FIR (First Information Report) ORM model."""
from __future__ import annotations

import uuid
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FIRReport(Base):
    __tablename__ = "fir_reports"

    fir_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    crime_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("crimes.id", ondelete="SET NULL"), nullable=True, index=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    # Raw text and file
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # NLP-extracted entities (stored as JSONB for flexibility)
    extracted_entities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # e.g. {"location": "...", "crime_type": "...", "weapon": "...", "suspects": [...]}

    # Confidence scores
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Processing status
    nlp_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )  # pending | processing | completed | failed

    # Relationships
    crime: Mapped[object | None] = relationship("Crime", back_populates="fir_report")
    submitted_by_user: Mapped[object] = relationship(
        "User", back_populates="fir_reports", foreign_keys=[submitted_by],
    )
