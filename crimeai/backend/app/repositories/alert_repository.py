"""Alert repository."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert


class AlertRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
        return result.scalar_one_or_none()

    async def list_alerts(
        self,
        is_resolved: bool | None = None,
        severity: str | None = None,
        alert_type: str | None = None,
        target_role: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Alert], int, int]:
        filters = []
        if is_resolved is not None:
            filters.append(Alert.is_resolved == is_resolved)
        if severity:
            filters.append(Alert.severity == severity)
        if alert_type:
            filters.append(Alert.alert_type == alert_type)
        if target_role:
            filters.append(
                (Alert.target_role == target_role) | (Alert.target_role.is_(None))
            )
        where = and_(*filters) if filters else True

        total = (await self.db.execute(
            select(func.count(Alert.id)).where(where)
        )).scalar_one()

        unread = (await self.db.execute(
            select(func.count(Alert.id)).where(
                and_(Alert.is_read == False, where) if filters else Alert.is_read == False
            )
        )).scalar_one()

        rows = (await self.db.execute(
            select(Alert)
            .where(where)
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .offset(offset)
        )).scalars().all()

        return list(rows), total, unread

    async def create(self, **kwargs: Any) -> Alert:
        alert = Alert(**kwargs)
        self.db.add(alert)
        await self.db.flush()
        await self.db.refresh(alert)
        return alert

    async def mark_read(self, alert_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Alert).where(Alert.id == alert_id).values(is_read=True)
        )

    async def mark_resolved(self, alert_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Alert)
            .where(Alert.id == alert_id)
            .values(is_resolved=True, is_read=True)
        )

    async def bulk_create(self, alerts: list[dict]) -> int:
        for a in alerts:
            self.db.add(Alert(**a))
        await self.db.flush()
        return len(alerts)
