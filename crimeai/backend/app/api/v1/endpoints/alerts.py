"""
Alert endpoints — CRUD + mark-read/resolve + WebSocket broadcast hook.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, require_role
from app.core.security import UserRole
from app.db.redis import get_redis
from app.db.session import get_db
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertCreateRequest, AlertListResponse, AlertResponse

router = APIRouter()


@router.get("/", response_model=AlertListResponse, summary="List alerts")
async def list_alerts(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    db: Annotated[AsyncSession, Depends(get_db)],
    is_resolved: bool | None = Query(None),
    severity: str | None = Query(None),
    alert_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AlertListResponse:
    repo = AlertRepository(db)
    items, total, unread = await repo.list_alerts(
        is_resolved=is_resolved,
        severity=severity,
        alert_type=alert_type,
        target_role=current_user.role,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in items],
        total=total,
        unread_count=unread,
    )


@router.post(
    "/",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual alert (Admin)",
)
async def create_alert(
    body: AlertCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AlertResponse:
    repo = AlertRepository(db)
    alert = await repo.create(
        title=body.title,
        message=body.message,
        alert_type=body.alert_type,
        severity=body.severity,
        latitude=body.latitude,
        longitude=body.longitude,
        district=body.district,
        related_crime_id=body.related_crime_id,
        target_role=body.target_role,
        assigned_to=body.assigned_to,
    )
    # Publish to WebSocket channel so connected clients get it instantly
    import json
    await redis.publish(
        "alerts:broadcast",
        json.dumps({
            "type": "new_alert",
            "alert_id": str(alert.id),
            "severity": alert.severity,
            "title": alert.title,
        }),
    )
    return AlertResponse.model_validate(alert)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertResponse:
    repo = AlertRepository(db)
    alert = await repo.get_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}/read", summary="Mark alert as read")
async def mark_read(
    alert_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    repo = AlertRepository(db)
    alert = await repo.get_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await repo.mark_read(alert_id)
    return {"message": "Alert marked as read", "alert_id": str(alert_id)}


@router.patch("/{alert_id}/resolve", summary="Resolve alert")
async def resolve_alert(
    alert_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    repo = AlertRepository(db)
    alert = await repo.get_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await repo.mark_resolved(alert_id)
    return {"message": "Alert resolved", "alert_id": str(alert_id)}
