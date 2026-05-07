"""
Crime endpoints — full CRUD + geo + stats + GeoJSON export.
All routes require at minimum POLICE role.
"""
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, get_current_user, require_role
from app.core.config import settings
from app.core.security import UserRole
from app.db.redis import get_redis
from app.db.session import get_db
from app.schemas.crime import (
    CrimeCreateRequest,
    CrimeFilterParams,
    CrimeListResponse,
    CrimeResponse,
    CrimeStatsResponse,
    CrimeUpdateRequest,
    GeoJSONFeatureCollection,
    NearbyFilterParams,
)
from app.services.crime_service import CrimeService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _get_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> CrimeService:
    return CrimeService(db=db, redis=redis)


# ── LIST ──────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=CrimeListResponse,
    summary="List crimes with filters and pagination",
)
async def list_crimes(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[CrimeService, Depends(_get_service)],
    crime_type: str | None = Query(None, description="Filter by crime type"),
    district: str | None = Query(None),
    city: str | None = Query(None),
    status: str | None = Query(None),
    severity_min: int | None = Query(None, ge=1, le=5),
    severity_max: int | None = Query(None, ge=1, le=5),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    cluster_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> CrimeListResponse:
    params = CrimeFilterParams(
        crime_type=crime_type,
        district=district,
        city=city,
        status=status,
        severity_min=severity_min,
        severity_max=severity_max,
        from_date=from_date,
        to_date=to_date,
        cluster_id=cluster_id,
        limit=limit,
        offset=offset,
    )
    return await service.list_crimes(params)


# ── STATS ─────────────────────────────────────────────────────────────────────

@router.get(
    "/stats",
    response_model=CrimeStatsResponse,
    summary="Aggregated crime statistics for dashboard",
)
async def get_crime_stats(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[CrimeService, Depends(_get_service)],
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    city: str | None = Query(None),
) -> CrimeStatsResponse:
    return await service.get_stats(
        from_date=from_date, to_date=to_date, city=city
    )


# ── HEATMAP ───────────────────────────────────────────────────────────────────

@router.get(
    "/heatmap",
    summary="Heatmap data points for Leaflet.heat",
)
async def get_heatmap(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[CrimeService, Depends(_get_service)],
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    crime_type: str | None = Query(None),
) -> list[dict]:
    return await service.get_heatmap_points(
        from_date=from_date, to_date=to_date, crime_type=crime_type
    )


# ── NEARBY ────────────────────────────────────────────────────────────────────

@router.get(
    "/nearby",
    response_model=list[CrimeResponse],
    summary="Crimes within radius of a point (PostGIS)",
)
async def crimes_nearby(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[CrimeService, Depends(_get_service)],
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(2.0, ge=0.1, le=50.0),
    crime_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[CrimeResponse]:
    params = NearbyFilterParams(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        crime_type=crime_type,
        limit=limit,
    )
    return await service.find_nearby(params)


# ── GEOJSON EXPORT ────────────────────────────────────────────────────────────

@router.get(
    "/export/geojson",
    response_class=JSONResponse,
    summary="Export crimes as GeoJSON FeatureCollection",
)
async def export_geojson(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))],
    service: Annotated[CrimeService, Depends(_get_service)],
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    crime_type: str | None = Query(None),
    district: str | None = Query(None),
) -> JSONResponse:
    collection = await service.export_geojson(
        from_date=from_date,
        to_date=to_date,
        crime_type=crime_type,
        district=district,
    )
    return JSONResponse(
        content=collection.model_dump(mode="json"),
        headers={
            "Content-Disposition": 'attachment; filename="crimes.geojson"',
            "Content-Type": "application/geo+json",
        },
    )


# ── GET BY ID ─────────────────────────────────────────────────────────────────

@router.get(
    "/{crime_id}",
    response_model=CrimeResponse,
    summary="Get a single crime record",
)
async def get_crime(
    crime_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[CrimeService, Depends(_get_service)],
) -> CrimeResponse:
    return await service.get_crime(crime_id)


# ── CREATE ────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=CrimeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new crime record",
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def create_crime(
    request: Request,
    body: CrimeCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[CrimeService, Depends(_get_service)],
) -> CrimeResponse:
    return await service.create_crime(body, created_by=current_user.user_id)


# ── UPDATE ────────────────────────────────────────────────────────────────────

@router.patch(
    "/{crime_id}",
    response_model=CrimeResponse,
    summary="Update a crime record (partial update)",
)
async def update_crime(
    crime_id: uuid.UUID,
    body: CrimeUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[CrimeService, Depends(_get_service)],
) -> CrimeResponse:
    return await service.update_crime(crime_id, body)


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.delete(
    "/{crime_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a crime record (Admin only)",
)
async def delete_crime(
    crime_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    service: Annotated[CrimeService, Depends(_get_service)],
) -> None:
    await service.delete_crime(crime_id)
