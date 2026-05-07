"""
Crime repository — all database operations for the Crime model.
Handles CRUD, geo queries, aggregations, and ML field updates.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2.functions import ST_AsGeoJSON, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import and_, case, cast, extract, func, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crime import Crime


class CrimeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Single-record lookups ─────────────────────────────────────────────────

    async def get_by_id(self, crime_id: uuid.UUID) -> Crime | None:
        result = await self.db.execute(
            select(Crime).where(Crime.id == crime_id)
        )
        return result.scalar_one_or_none()

    async def get_by_case_number(self, case_number: str) -> Crime | None:
        result = await self.db.execute(
            select(Crime).where(Crime.case_number == case_number)
        )
        return result.scalar_one_or_none()

    # ── Filtered list ─────────────────────────────────────────────────────────

    async def list_crimes(
        self,
        crime_type: str | None = None,
        district: str | None = None,
        city: str | None = None,
        status: str | None = None,
        severity_min: int | None = None,
        severity_max: int | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        assigned_officer_id: uuid.UUID | None = None,
        cluster_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Crime], int]:
        """Returns (items, total_count) for pagination."""
        filters = self._build_filters(
            crime_type=crime_type,
            district=district,
            city=city,
            status=status,
            severity_min=severity_min,
            severity_max=severity_max,
            from_date=from_date,
            to_date=to_date,
            assigned_officer_id=assigned_officer_id,
            cluster_id=cluster_id,
        )

        # Count query
        count_q = select(func.count(Crime.id))
        if filters:
            count_q = count_q.where(and_(*filters))
        total_result = await self.db.execute(count_q)
        total = total_result.scalar_one()

        # Data query
        data_q = select(Crime)
        if filters:
            data_q = data_q.where(and_(*filters))
        data_q = data_q.order_by(Crime.occurred_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(data_q)
        return list(result.scalars().all()), total

    def _build_filters(self, **kwargs: Any) -> list:
        filters = []
        if kwargs.get("crime_type"):
            filters.append(Crime.crime_type == kwargs["crime_type"])
        if kwargs.get("district"):
            filters.append(Crime.district == kwargs["district"])
        if kwargs.get("city"):
            filters.append(Crime.city == kwargs["city"])
        if kwargs.get("status"):
            filters.append(Crime.status == kwargs["status"])
        if kwargs.get("severity_min") is not None:
            filters.append(Crime.severity >= kwargs["severity_min"])
        if kwargs.get("severity_max") is not None:
            filters.append(Crime.severity <= kwargs["severity_max"])
        if kwargs.get("from_date"):
            filters.append(Crime.occurred_at >= kwargs["from_date"])
        if kwargs.get("to_date"):
            filters.append(Crime.occurred_at <= kwargs["to_date"])
        if kwargs.get("assigned_officer_id"):
            filters.append(Crime.assigned_officer_id == kwargs["assigned_officer_id"])
        if kwargs.get("cluster_id") is not None:
            filters.append(Crime.cluster_id == kwargs["cluster_id"])
        return filters

    # ── Geo queries ───────────────────────────────────────────────────────────

    async def find_within_radius(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        crime_type: str | None = None,
        limit: int = 100,
    ) -> list[Crime]:
        """PostGIS ST_DWithin — finds crimes within radius_km of point."""
        point = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        # Cast to geography so distance is in metres (not degrees)
        geo_col = func.cast(Crime.geom, func.Geography.type)
        geo_pt = func.cast(point, func.Geography.type)

        query = select(Crime).where(
            ST_DWithin(geo_col, geo_pt, radius_km * 1000)
        )
        if crime_type:
            query = query.where(Crime.crime_type == crime_type)
        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_all_coordinates(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict]:
        """Return minimal lat/lng rows for ML clustering — no ORM overhead."""
        query = select(
            Crime.id,
            Crime.latitude,
            Crime.longitude,
            Crime.crime_type,
            Crime.severity,
            Crime.occurred_at,
        )
        if from_date:
            query = query.where(Crime.occurred_at >= from_date)
        if to_date:
            query = query.where(Crime.occurred_at <= to_date)
        result = await self.db.execute(query)
        return [
            {
                "id": str(r.id),
                "lat": float(r.latitude),
                "lng": float(r.longitude),
                "crime_type": r.crime_type,
                "severity": r.severity,
                "occurred_at": r.occurred_at.isoformat(),
            }
            for r in result.all()
        ]

    # ── Aggregations ──────────────────────────────────────────────────────────

    async def get_stats(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        city: str | None = None,
    ) -> dict:
        """Dashboard statistics — all in one DB round trip."""
        filters = []
        if from_date:
            filters.append(Crime.occurred_at >= from_date)
        if to_date:
            filters.append(Crime.occurred_at <= to_date)
        if city:
            filters.append(Crime.city == city)
        where = and_(*filters) if filters else True

        # By crime type
        type_q = (
            select(Crime.crime_type, func.count(Crime.id).label("cnt"))
            .where(where)
            .group_by(Crime.crime_type)
            .order_by(func.count(Crime.id).desc())
        )
        type_rows = (await self.db.execute(type_q)).all()

        # By district
        district_q = (
            select(Crime.district, func.count(Crime.id).label("cnt"))
            .where(where)
            .group_by(Crime.district)
            .order_by(func.count(Crime.id).desc())
        )
        district_rows = (await self.db.execute(district_q)).all()

        # By status
        status_q = (
            select(Crime.status, func.count(Crime.id).label("cnt"))
            .where(where)
            .group_by(Crime.status)
        )
        status_rows = (await self.db.execute(status_q)).all()

        # By severity
        severity_q = (
            select(Crime.severity, func.count(Crime.id).label("cnt"))
            .where(where)
            .group_by(Crime.severity)
            .order_by(Crime.severity)
        )
        severity_rows = (await self.db.execute(severity_q)).all()

        # By month (last 12)
        month_q = (
            select(
                extract("year", Crime.occurred_at).label("year"),
                extract("month", Crime.occurred_at).label("month"),
                func.count(Crime.id).label("cnt"),
            )
            .where(where)
            .group_by(
                extract("year", Crime.occurred_at),
                extract("month", Crime.occurred_at),
            )
            .order_by(
                extract("year", Crime.occurred_at),
                extract("month", Crime.occurred_at),
            )
            .limit(12)
        )
        month_rows = (await self.db.execute(month_q)).all()

        # Total count
        total_q = select(func.count(Crime.id)).where(where)
        total = (await self.db.execute(total_q)).scalar_one()

        # Avg daily
        if month_rows:
            days = max(
                (to_date - from_date).days if from_date and to_date else 30, 1
            )
            avg_daily = total / days
        else:
            avg_daily = 0.0

        # Most active hour
        hour_q = (
            select(
                extract("hour", Crime.occurred_at).label("hr"),
                func.count(Crime.id).label("cnt"),
            )
            .where(where)
            .group_by(extract("hour", Crime.occurred_at))
            .order_by(func.count(Crime.id).desc())
            .limit(1)
        )
        hour_row = (await self.db.execute(hour_q)).first()

        return {
            "total_crimes": total,
            "by_type": {r.crime_type: r.cnt for r in type_rows},
            "by_district": {(r.district or "Unknown"): r.cnt for r in district_rows},
            "by_status": {r.status: r.cnt for r in status_rows},
            "by_severity": {str(r.severity): r.cnt for r in severity_rows},
            "by_month": [
                {"year": int(r.year), "month": int(r.month), "count": r.cnt}
                for r in month_rows
            ],
            "avg_daily_crimes": round(avg_daily, 2),
            "most_active_hour": int(hour_row.hr) if hour_row else 0,
        }

    async def get_hotspot_data(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        city: str | None = None,
    ) -> list[dict]:
        """District-level heatmap data: count + centroid."""
        filters = []
        if from_date:
            filters.append(Crime.occurred_at >= from_date)
        if to_date:
            filters.append(Crime.occurred_at <= to_date)
        if city:
            filters.append(Crime.city == city)
        where = and_(*filters) if filters else True

        query = (
            select(
                Crime.district,
                Crime.crime_type,
                func.count(Crime.id).label("count"),
                func.avg(Crime.latitude).label("avg_lat"),
                func.avg(Crime.longitude).label("avg_lng"),
                func.max(Crime.severity).label("max_severity"),
            )
            .where(where)
            .group_by(Crime.district, Crime.crime_type)
            .order_by(func.count(Crime.id).desc())
        )
        result = await self.db.execute(query)
        return [
            {
                "district": r.district or "Unknown",
                "crime_type": r.crime_type,
                "count": r.count,
                "lat": float(r.avg_lat or 0),
                "lng": float(r.avg_lng or 0),
                "max_severity": r.max_severity,
            }
            for r in result.all()
        ]

    # ── Heatmap points ────────────────────────────────────────────────────────

    async def get_heatmap_points(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        crime_type: str | None = None,
    ) -> list[dict]:
        """Return [lat, lng, weight] for Leaflet.heat plugin."""
        filters = []
        if from_date:
            filters.append(Crime.occurred_at >= from_date)
        if to_date:
            filters.append(Crime.occurred_at <= to_date)
        if crime_type:
            filters.append(Crime.crime_type == crime_type)
        where = and_(*filters) if filters else True

        query = select(
            Crime.latitude,
            Crime.longitude,
            Crime.severity,
        ).where(where)

        result = await self.db.execute(query)
        return [
            {
                "lat": float(r.latitude),
                "lng": float(r.longitude),
                "weight": float(r.severity) / 5.0,
            }
            for r in result.all()
        ]

    # ── Write operations ──────────────────────────────────────────────────────

    async def create(
        self,
        crime_type: str,
        city: str,
        latitude: float,
        longitude: float,
        occurred_at: datetime,
        **kwargs: Any,
    ) -> Crime:
        crime = Crime(
            crime_type=crime_type,
            city=city,
            latitude=latitude,
            longitude=longitude,
            occurred_at=occurred_at,
            geom=f"SRID=4326;POINT({longitude} {latitude})",
            **kwargs,
        )
        self.db.add(crime)
        await self.db.flush()
        await self.db.refresh(crime)
        return crime

    async def update(
        self, crime_id: uuid.UUID, updates: dict[str, Any]
    ) -> Crime | None:
        # If lat/lng updated, also update geom
        if "latitude" in updates and "longitude" in updates:
            updates["geom"] = (
                f"SRID=4326;POINT({updates['longitude']} {updates['latitude']})"
            )
        await self.db.execute(
            update(Crime).where(Crime.id == crime_id).values(**updates)
        )
        return await self.get_by_id(crime_id)

    async def delete(self, crime_id: uuid.UUID) -> bool:
        crime = await self.get_by_id(crime_id)
        if not crime:
            return False
        await self.db.delete(crime)
        await self.db.flush()
        return True

    async def bulk_update_clusters(
        self, assignments: list[dict]  # [{"id": str, "cluster_id": int}]
    ) -> int:
        """Bulk-update cluster IDs from DBSCAN output."""
        updated = 0
        for row in assignments:
            await self.db.execute(
                update(Crime)
                .where(Crime.id == uuid.UUID(row["id"]))
                .values(cluster_id=row["cluster_id"])
            )
            updated += 1
        await self.db.flush()
        return updated

    async def update_risk_score(
        self, crime_id: uuid.UUID, risk_score: float
    ) -> None:
        """Update risk_score for a single crime. Used by score_crime_risk task."""
        await self.db.execute(
            update(Crime)
            .where(Crime.id == crime_id)
            .values(risk_score=risk_score)
        )
        await self.db.flush()

    async def bulk_update_risk_scores(
        self, scores: list[dict]  # [{"id": str, "risk_score": float}]
    ) -> int:
        updated = 0
        for row in scores:
            await self.db.execute(
                update(Crime)
                .where(Crime.id == uuid.UUID(row["id"]))
                .values(risk_score=row["risk_score"])
            )
            updated += 1
        await self.db.flush()
        return updated

    async def count(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> int:
        query = select(func.count(Crime.id))
        if from_date:
            query = query.where(Crime.occurred_at >= from_date)
        if to_date:
            query = query.where(Crime.occurred_at <= to_date)
        result = await self.db.execute(query)
        return result.scalar_one()

    # ── GeoJSON export ────────────────────────────────────────────────────────

    async def export_geojson(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        crime_type: str | None = None,
        district: str | None = None,
        limit: int = 5000,
    ) -> list[dict]:
        """Raw crime data formatted for GeoJSON FeatureCollection."""
        filters = []
        if from_date:
            filters.append(Crime.occurred_at >= from_date)
        if to_date:
            filters.append(Crime.occurred_at <= to_date)
        if crime_type:
            filters.append(Crime.crime_type == crime_type)
        if district:
            filters.append(Crime.district == district)
        where = and_(*filters) if filters else True

        query = (
            select(Crime)
            .where(where)
            .order_by(Crime.occurred_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())
