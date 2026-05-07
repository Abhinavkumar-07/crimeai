"""Pydantic schemas for FIR endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FIRCreateRequest(BaseModel):
    fir_number: str = Field(..., min_length=3, max_length=50)
    raw_text: str = Field(..., min_length=20, max_length=50000)
    crime_id: uuid.UUID | None = None


class FIRResponse(BaseModel):
    id: uuid.UUID
    fir_number: str
    crime_id: uuid.UUID | None
    submitted_by: uuid.UUID
    raw_text: str
    file_url: str | None
    extracted_entities: dict[str, Any] | None
    extraction_confidence: float | None
    nlp_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FIRListResponse(BaseModel):
    items: list[FIRResponse]
    total: int
