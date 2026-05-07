"""
ML endpoints — full implementation replacing the stub from Step 2.
Delegates all heavy computation to MLService and Celery workers.
"""
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from redis.asyncio import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, require_role
from app.core.config import settings
from app.core.security import UserRole
from app.db.redis import get_redis
from app.db.session import get_db
from app.services.ml_service import MLService
from app.workers.tasks.ml_tasks import (
    run_crime_clustering,
    run_hotspot_prediction,
    score_crime_risk,
)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _get_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> MLService:
    return MLService(db=db, redis=redis)


# ── Clustering ────────────────────────────────────────────────────────────────

@router.post(
    "/cluster",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger DBSCAN crime clustering (Analyst+)",
)
@limiter.limit(settings.RATE_LIMIT_ML)
async def trigger_clustering(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))],
    eps_km: float | None = Query(None, ge=0.1, le=20.0, description="Neighbourhood radius in km"),
    min_samples: int | None = Query(None, ge=2, le=20),
    auto_eps: bool = Query(False, description="Auto-detect optimal eps via elbow method"),
    from_date: datetime | None = Query(None),
) -> dict:
    """
    Queues a background DBSCAN clustering job.
    Returns task_id to poll for completion.
    """
    task = run_crime_clustering.apply_async(
        kwargs={
            "eps_km": eps_km,
            "min_samples": min_samples,
            "auto_eps": auto_eps,
            "from_date_iso": from_date.isoformat() if from_date else None,
        },
        queue="ml",
    )
    return {
        "message": "Clustering job queued",
        "task_id": task.id,
        "status_url": f"/api/v1/ml/tasks/{task.id}",
        "params": {"eps_km": eps_km, "min_samples": min_samples, "auto_eps": auto_eps},
    }


@router.get("/clusters", summary="Get current cluster results (Police+)")
async def get_clusters(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[MLService, Depends(_get_service)],
) -> dict:
    """Returns cached DBSCAN results. Includes cluster centroids and summaries."""
    return await service.get_clusters()


# ── Hotspot prediction ────────────────────────────────────────────────────────

@router.post(
    "/hotspot-prediction",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Train hotspot model + predict next 24h (Analyst+)",
)
@limiter.limit(settings.RATE_LIMIT_ML)
async def trigger_hotspot_prediction(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))],
) -> dict:
    task = run_hotspot_prediction.apply_async(queue="ml")
    return {
        "message": "Hotspot prediction job queued",
        "task_id": task.id,
        "status_url": f"/api/v1/ml/tasks/{task.id}",
    }


@router.get(
    "/hotspot-predictions",
    summary="Get 24h hotspot forecast (Police+)",
)
async def get_hotspot_predictions(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[MLService, Depends(_get_service)],
) -> dict:
    return await service.get_hotspot_predictions()


# ── Risk map ──────────────────────────────────────────────────────────────────

@router.get(
    "/risk-map",
    summary="District risk scores (Police+)",
)
async def get_risk_map(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[MLService, Depends(_get_service)],
) -> dict:
    """
    Returns composite risk score per district (0–100) with breakdown:
    - total crimes, recent activity, severity trend, escalation score
    """
    return await service.get_risk_map()


# ── Similarity search ─────────────────────────────────────────────────────────

@router.post(
    "/similarity",
    summary="Find crimes similar to a text description (Analyst+)",
)
async def find_similar_crimes(
    body: dict,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))],
    service: Annotated[MLService, Depends(_get_service)],
) -> list[dict]:
    """
    Embed query text and search pgvector for similar crime descriptions.
    Body: {"text": "...", "top_k": 5, "crime_type": null, "min_similarity": 0.5}
    """
    query_text = body.get("text", "")
    if len(query_text) < 10:
        return []
    return await service.find_similar(
        query_text=query_text,
        top_k=int(body.get("top_k", 5)),
        crime_type_filter=body.get("crime_type"),
        min_similarity=float(body.get("min_similarity", 0.5)),
    )


@router.post(
    "/embed-crimes",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch-embed all un-embedded crimes (Admin)",
)
async def batch_embed(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    service: Annotated[MLService, Depends(_get_service)],
    limit: int = Query(1000, ge=1, le=5000),
) -> dict:
    result = await service.run_batch_embedding(limit=limit)
    return {"message": "Batch embedding complete", **result}


# ── Area profile ──────────────────────────────────────────────────────────────

@router.get(
    "/profile/{district}",
    summary="Behavioral pattern profile for a district (Analyst+)",
)
async def get_area_profile(
    district: str,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))],
    service: Annotated[MLService, Depends(_get_service)],
    lookback_days: int = Query(60, ge=7, le=365),
) -> dict:
    """
    Temporal signature, dominant crime types, severity trend,
    geographic hotspot within district, predicted next-crime window.
    """
    return await service.get_area_profile(district=district, lookback_days=lookback_days)


# ── Task polling ──────────────────────────────────────────────────────────────

@router.get(
    "/tasks/{task_id}",
    summary="Poll background task status",
)
async def get_task_status(
    task_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))],
) -> dict:
    from celery.result import AsyncResult
    from app.workers.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)
    response: dict = {"task_id": task_id, "status": result.status}
    if result.ready():
        if result.successful():
            response["result"] = result.get()
        else:
            response["error"] = str(result.info)
    return response


# ── Model info ────────────────────────────────────────────────────────────────

@router.get(
    "/model-info",
    summary="Current model metadata (Admin)",
)
async def get_model_info(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    service: Annotated[MLService, Depends(_get_service)],
) -> dict:
    return await service.get_model_info()
