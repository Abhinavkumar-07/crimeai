"""
Crime service — business logic layer.
Sits between endpoints and repository.
Handles: caching, case number generation, cache invalidation, GeoJSON assembly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.core.logging import get_logger
from app.db.redis import CacheManager
from app.repositories.crime_repository import CrimeRepository
from app.schemas.crime import (
    CrimeCreateRequest,
    CrimeFilterParams,
    CrimeListResponse,
    CrimeResponse,
    CrimeStatsResponse,
    CrimeUpdateRequest,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONFeatureProperties,
    GeoJSONPoint,
    NearbyFilterParams,
)

logger = get_logger(__name__)

# Cache TTLs
_STATS_TTL = 300        # 5 min
_HOTSPOT_TTL = 600      # 10 min
_HEATMAP_TTL = 600      # 10 min
_CRIME_TTL = 120        # 2 min per individual crime


class CrimeService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.repo = CrimeRepository(db)
        self.cache = CacheManager(redis, namespace="crimes")

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_crime(self, crime_id: uuid.UUID) -> CrimeResponse:
        cache_key = f"crime:{crime_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return CrimeResponse(**cached)

        crime = await self.repo.get_by_id(crime_id)
        if not crime:
            raise NotFoundError(f"Crime {crime_id} not found")

        response = CrimeResponse.model_validate(crime)
        await self.cache.set(cache_key, response.model_dump(mode="json"), ttl=_CRIME_TTL)
        return response

    async def list_crimes(
        self, params: CrimeFilterParams
    ) -> CrimeListResponse:
        crimes, total = await self.repo.list_crimes(
            crime_type=params.crime_type,
            district=params.district,
            city=params.city,
            status=params.status,
            severity_min=params.severity_min,
            severity_max=params.severity_max,
            from_date=params.from_date,
            to_date=params.to_date,
            assigned_officer_id=params.assigned_officer_id,
            cluster_id=params.cluster_id,
            limit=params.limit,
            offset=params.offset,
        )
        return CrimeListResponse(
            items=[CrimeResponse.model_validate(c) for c in crimes],
            total=total,
            limit=params.limit,
            offset=params.offset,
            has_more=(params.offset + params.limit) < total,
        )

    async def find_nearby(
        self, params: NearbyFilterParams
    ) -> list[CrimeResponse]:
        crimes = await self.repo.find_within_radius(
            latitude=params.latitude,
            longitude=params.longitude,
            radius_km=params.radius_km,
            crime_type=params.crime_type,
            limit=params.limit,
        )
        return [CrimeResponse.model_validate(c) for c in crimes]

    async def get_stats(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        city: str | None = None,
    ) -> CrimeStatsResponse:
        cache_key = f"stats:{city or 'all'}:{from_date}:{to_date}"
        cached = await self.cache.get(cache_key)
        if cached:
            return CrimeStatsResponse(**cached)

        stats = await self.repo.get_stats(
            from_date=from_date, to_date=to_date, city=city
        )
        response = CrimeStatsResponse(**stats)
        await self.cache.set(
            cache_key, response.model_dump(mode="json"), ttl=_STATS_TTL
        )
        return response

    async def get_hotspot_data(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        city: str | None = None,
    ) -> list[dict]:
        cache_key = f"hotspots:{city or 'all'}:{from_date}:{to_date}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        data = await self.repo.get_hotspot_data(
            from_date=from_date, to_date=to_date, city=city
        )
        await self.cache.set(cache_key, data, ttl=_HOTSPOT_TTL)
        return data

    async def get_heatmap_points(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        crime_type: str | None = None,
    ) -> list[dict]:
        cache_key = f"heatmap:{crime_type or 'all'}:{from_date}:{to_date}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        points = await self.repo.get_heatmap_points(
            from_date=from_date, to_date=to_date, crime_type=crime_type
        )
        await self.cache.set(cache_key, points, ttl=_HEATMAP_TTL)
        return points

    async def export_geojson(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        crime_type: str | None = None,
        district: str | None = None,
    ) -> GeoJSONFeatureCollection:
        crimes = await self.repo.export_geojson(
            from_date=from_date,
            to_date=to_date,
            crime_type=crime_type,
            district=district,
        )

        features = [
            GeoJSONFeature(
                geometry=GeoJSONPoint(
                    coordinates=[c.longitude, c.latitude]
                ),
                properties=GeoJSONFeatureProperties(
                    id=str(c.id),
                    crime_type=c.crime_type,
                    sub_type=c.sub_type,
                    severity=c.severity,
                    district=c.district,
                    city=c.city,
                    status=c.status,
                    occurred_at=c.occurred_at.isoformat(),
                    case_number=c.case_number,
                    risk_score=c.risk_score,
                ),
            )
            for c in crimes
        ]

        return GeoJSONFeatureCollection(
            features=features,
            metadata={
                "total": len(features),
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "filters": {
                    "crime_type": crime_type,
                    "district": district,
                    "from_date": from_date.isoformat() if from_date else None,
                    "to_date": to_date.isoformat() if to_date else None,
                },
            },
        )

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create_crime(
        self, data: CrimeCreateRequest, created_by: uuid.UUID
    ) -> CrimeResponse:
        # Check for duplicate case number
        if data.case_number:
            existing = await self.repo.get_by_case_number(data.case_number)
            if existing:
                raise AlreadyExistsError(
                    f"Case number '{data.case_number}' already exists",
                    detail={"existing_id": str(existing.id)},
                )

        # Auto-generate case number if not provided
        case_number = data.case_number or self._generate_case_number()

        # Build description — append weapon/suspect info if provided
        description = data.description or ""
        if data.weapon_used:
            description += f" Weapon used: {data.weapon_used}."
        if data.num_suspects:
            description += f" Number of suspects: {data.num_suspects}."

        crime = await self.repo.create(
            crime_type=data.crime_type,
            sub_type=data.sub_type,
            description=description.strip() or None,
            severity=data.severity,
            latitude=data.latitude,
            longitude=data.longitude,
            location_name=data.location_name,
            address=data.address,
            district=data.district,
            city=data.city,
            occurred_at=data.occurred_at,
            status=data.status,
            case_number=case_number,
            assigned_officer_id=data.assigned_officer_id,
        )

        logger.info(
            "crime_created",
            crime_id=str(crime.id),
            case_number=case_number,
            crime_type=data.crime_type,
            created_by=str(created_by),
        )

        # Invalidate stats/hotspot caches
        await self._invalidate_aggregate_caches()

        return CrimeResponse.model_validate(crime)

    async def update_crime(
        self, crime_id: uuid.UUID, data: CrimeUpdateRequest
    ) -> CrimeResponse:
        existing = await self.repo.get_by_id(crime_id)
        if not existing:
            raise NotFoundError(f"Crime {crime_id} not found")

        # Check case number uniqueness if changing it
        if data.case_number and data.case_number != existing.case_number:
            duplicate = await self.repo.get_by_case_number(data.case_number)
            if duplicate:
                raise AlreadyExistsError(
                    f"Case number '{data.case_number}' already in use"
                )

        updates = data.model_dump(exclude_none=True)
        if not updates:
            return CrimeResponse.model_validate(existing)

        updated = await self.repo.update(crime_id, updates)
        if not updated:
            raise NotFoundError(f"Crime {crime_id} not found after update")

        # Bust individual + aggregate caches
        await self.cache.delete(f"crime:{crime_id}")
        await self._invalidate_aggregate_caches()

        logger.info("crime_updated", crime_id=str(crime_id))
        return CrimeResponse.model_validate(updated)

    async def delete_crime(self, crime_id: uuid.UUID) -> None:
        deleted = await self.repo.delete(crime_id)
        if not deleted:
            raise NotFoundError(f"Crime {crime_id} not found")

        await self.cache.delete(f"crime:{crime_id}")
        await self._invalidate_aggregate_caches()
        logger.info("crime_deleted", crime_id=str(crime_id))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _generate_case_number(self) -> str:
        year = datetime.now(timezone.utc).year
        suffix = str(uuid.uuid4())[:8].upper()
        return f"CRM-{year}-{suffix}"

    async def _invalidate_aggregate_caches(self) -> None:
        await self.cache.invalidate_pattern("stats:*")
        await self.cache.invalidate_pattern("hotspots:*")
        await self.cache.invalidate_pattern("heatmap:*")
