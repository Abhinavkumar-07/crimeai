"""FIR report repository."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fir import FIRReport


class FIRRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, fir_id: uuid.UUID) -> FIRReport | None:
        result = await self.db.execute(select(FIRReport).where(FIRReport.id == fir_id))
        return result.scalar_one_or_none()

    async def get_by_fir_number(self, fir_number: str) -> FIRReport | None:
        result = await self.db.execute(
            select(FIRReport).where(FIRReport.fir_number == fir_number)
        )
        return result.scalar_one_or_none()

    async def list_firs(
        self,
        nlp_status: str | None = None,
        submitted_by: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FIRReport], int]:
        query = select(FIRReport)
        count_q = select(func.count(FIRReport.id))
        if nlp_status:
            query = query.where(FIRReport.nlp_status == nlp_status)
            count_q = count_q.where(FIRReport.nlp_status == nlp_status)
        if submitted_by:
            query = query.where(FIRReport.submitted_by == submitted_by)
            count_q = count_q.where(FIRReport.submitted_by == submitted_by)
        total = (await self.db.execute(count_q)).scalar_one()
        rows = (
            await self.db.execute(
                query.order_by(FIRReport.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), total

    async def create(self, **kwargs: Any) -> FIRReport:
        fir = FIRReport(**kwargs)
        self.db.add(fir)
        await self.db.flush()
        await self.db.refresh(fir)
        return fir

    async def update_nlp_result(
        self,
        fir_id: uuid.UUID,
        entities: dict,
        confidence: float,
        status: str = "completed",
    ) -> None:
        await self.db.execute(
            update(FIRReport)
            .where(FIRReport.id == fir_id)
            .values(
                extracted_entities=entities,
                extraction_confidence=confidence,
                nlp_status=status,
            )
        )

    async def set_nlp_status(self, fir_id: uuid.UUID, status: str) -> None:
        await self.db.execute(
            update(FIRReport).where(FIRReport.id == fir_id).values(nlp_status=status)
        )
