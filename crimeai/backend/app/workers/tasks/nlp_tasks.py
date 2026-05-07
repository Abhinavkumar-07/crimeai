"""
Celery NLP tasks — full implementation.
Processes FIR queue asynchronously so API responses stay fast.
"""
from __future__ import annotations

import asyncio
import uuid

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


async def _get_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
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
    name="app.workers.tasks.nlp_tasks.process_fir",
    max_retries=3,
    default_retry_delay=30,
    queue="nlp",
)
def process_fir(self, fir_id: str) -> dict:
    """
    On-demand task: run NLP pipeline on a FIR and persist results.
    Triggered immediately after FIR submission via /fir/ endpoint.
    """
    logger.info("nlp_fir_task_started", fir_id=fir_id, task_id=self.request.id)

    async def _run():
        db, redis, engine = await _get_session()
        try:
            from app.services.nlp_service import NLPService
            svc = NLPService(db=db, redis=redis)
            result = await svc.process_fir(uuid.UUID(fir_id))
            await db.commit()
            return {"status": "completed", "fir_id": fir_id, "crime_type": result.get("crime_type")}
        except Exception as exc:
            await db.rollback()
            raise exc
        finally:
            await db.close()
            await engine.dispose()

    try:
        result = _run_async(_run())
        logger.info("nlp_fir_task_complete", fir_id=fir_id, **result)
        return result
    except Exception as exc:
        logger.error("nlp_fir_task_failed", fir_id=fir_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.workers.tasks.nlp_tasks.process_pending_firs",
    max_retries=2,
    queue="nlp",
)
def process_pending_firs(self) -> dict:
    """
    Scheduled task: pick up any FIRs stuck in 'pending' state
    (e.g., if the worker was down when they were submitted).
    """
    logger.info("process_pending_firs_started")

    async def _run():
        db, redis, engine = await _get_session()
        try:
            from app.services.nlp_service import NLPService
            svc = NLPService(db=db, redis=redis)
            pending = await svc.get_pending_firs()

            processed = 0
            errors = 0
            for item in pending:
                try:
                    await svc.process_fir(uuid.UUID(item["fir_id"]))
                    await db.commit()
                    processed += 1
                except Exception as exc:
                    await db.rollback()
                    logger.warning(
                        "pending_fir_process_failed",
                        fir_id=item["fir_id"],
                        error=str(exc),
                    )
                    errors += 1

            return {"total": len(pending), "processed": processed, "errors": errors}
        finally:
            await db.close()
            await engine.dispose()

    try:
        result = _run_async(_run())
        logger.info("process_pending_firs_complete", **result)
        return result
    except Exception as exc:
        logger.error("process_pending_firs_failed", error=str(exc))
        raise self.retry(exc=exc)
