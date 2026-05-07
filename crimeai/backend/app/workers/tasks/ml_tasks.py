"""
Celery ML tasks — full implementation replacing Step 1 stubs.
Each task creates its own DB session and Redis connection
(Celery workers are separate processes from the FastAPI app).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _get_db_and_redis():
    """Create DB session and Redis client for use inside Celery task."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from app.core.config import settings
    from app.db.redis import get_redis_pool

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    db = Session()
    redis = await get_redis_pool()
    return db, redis, engine


@shared_task(
    bind=True,
    name="app.workers.tasks.ml_tasks.run_hotspot_prediction",
    max_retries=3,
    default_retry_delay=60,
    queue="ml",
)
def run_hotspot_prediction(self) -> dict:
    """
    Scheduled: train hotspot model + compute 24h predictions + risk map.
    Writes results to Redis cache and updates crime risk_score column.
    """
    logger.info("hotspot_prediction_task_started", task_id=self.request.id)

    async def _run():
        db, redis, engine = await _get_db_and_redis()
        try:
            from app.services.ml_service import MLService
            svc = MLService(db=db, redis=redis)
            result = await svc.train_and_predict_hotspots()
            await db.commit()
            return result
        except Exception as exc:
            await db.rollback()
            raise exc
        finally:
            await db.close()
            await engine.dispose()

    try:
        result = _run_async(_run())
        logger.info("hotspot_prediction_task_complete", result_status=result.get("status"))
        return result
    except Exception as exc:
        logger.error("hotspot_prediction_task_failed", error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.workers.tasks.ml_tasks.run_crime_clustering",
    max_retries=3,
    default_retry_delay=30,
    queue="ml",
)
def run_crime_clustering(
    self,
    eps_km: float | None = None,
    min_samples: int | None = None,
    auto_eps: bool = False,
    from_date_iso: str | None = None,
) -> dict:
    """
    Scheduled + on-demand: DBSCAN clustering on all recent crimes.
    Writes cluster_id back to crimes table.
    """
    logger.info(
        "crime_clustering_task_started",
        task_id=self.request.id,
        eps_km=eps_km,
        auto_eps=auto_eps,
    )

    from_date = datetime.fromisoformat(from_date_iso) if from_date_iso else None

    async def _run():
        db, redis, engine = await _get_db_and_redis()
        try:
            from app.services.ml_service import MLService
            svc = MLService(db=db, redis=redis)
            result = await svc.run_clustering(
                eps_km=eps_km,
                min_samples=min_samples,
                from_date=from_date,
                auto_eps=auto_eps,
            )
            await db.commit()
            return result
        except Exception as exc:
            await db.rollback()
            raise exc
        finally:
            await db.close()
            await engine.dispose()

    try:
        result = _run_async(_run())
        logger.info(
            "crime_clustering_task_complete",
            n_clusters=result.get("n_clusters"),
        )
        return result
    except Exception as exc:
        logger.error("crime_clustering_task_failed", error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.workers.tasks.ml_tasks.score_crime_risk",
    max_retries=2,
    default_retry_delay=10,
    queue="ml",
)
def score_crime_risk(self, crime_id: str) -> dict:
    """
    On-demand: compute risk score for a single newly-created crime
    and update its row. Called after crime creation.
    """
    logger.info("risk_scoring_task_started", crime_id=crime_id)

    async def _run():
        db, redis, engine = await _get_db_and_redis()
        try:
            from app.repositories.crime_repository import CrimeRepository
            from app.ml.prediction.risk_scorer import score_single_crime
            import uuid

            repo = CrimeRepository(db)
            crime = await repo.get_by_id(uuid.UUID(crime_id))
            if not crime:
                return {"status": "not_found", "crime_id": crime_id}

            risk_score = score_single_crime(
                crime_type=crime.crime_type,
                severity=crime.severity,
                district=crime.district or "Unknown",
                occurred_at=crime.occurred_at,
            )
            await repo.update_risk_score(crime.id, risk_score)
            await db.commit()
            return {"status": "complete", "crime_id": crime_id, "risk_score": risk_score}
        except Exception as exc:
            await db.rollback()
            raise exc
        finally:
            await db.close()
            await engine.dispose()

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("risk_scoring_task_failed", crime_id=crime_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.workers.tasks.ml_tasks.run_batch_embedding",
    max_retries=2,
    queue="ml",
)
def run_batch_embedding(self, limit: int = 500) -> dict:
    """Batch-embed all crimes lacking embeddings."""
    logger.info("batch_embedding_task_started", limit=limit)

    async def _run():
        db, redis, engine = await _get_db_and_redis()
        try:
            from app.ml.similarity.crime_similarity import batch_embed_crimes
            result = await batch_embed_crimes(db, limit=limit)
            return result
        finally:
            await db.close()
            await engine.dispose()

    try:
        result = _run_async(_run())
        logger.info("batch_embedding_task_complete", **result)
        return result
    except Exception as exc:
        logger.error("batch_embedding_task_failed", error=str(exc))
        raise self.retry(exc=exc)
