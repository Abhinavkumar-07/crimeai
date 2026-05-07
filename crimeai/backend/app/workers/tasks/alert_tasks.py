"""
Celery alert tasks — full implementation.
Checks for high-risk areas and fires alerts via Redis pub/sub.
"""
from __future__ import annotations

import asyncio
import json

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@shared_task(name="app.workers.tasks.alert_tasks.check_high_risk_areas")
def check_high_risk_areas() -> dict:
    """
    Scheduled every 15 minutes.
    Checks risk scores and fires alerts for districts that crossed a threshold.
    """
    logger.info("alert_check_started")

    async def _run():
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool
        from app.core.config import settings
        from app.db.redis import get_redis_pool
        from app.ml.prediction.risk_scorer import get_cached_risk_scores
        from app.repositories.alert_repository import AlertRepository

        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        db = Session()
        redis = await get_redis_pool()

        try:
            risk_scores = get_cached_risk_scores()
            if not risk_scores:
                return {"status": "no_risk_data"}

            # Find districts that crossed HIGH threshold (score >= 70)
            alerts_fired = 0
            repo = AlertRepository(db)

            for district, data in risk_scores.items():
                score = data.get("score", 0)
                level = data.get("level", "low")

                if level in ("high", "critical"):
                    # Check if we already fired an alert for this district recently
                    cache_key = f"alert_fired:{district}"
                    already_fired = await redis.get(cache_key)
                    if already_fired:
                        continue

                    alert = await repo.create(
                        title=f"{'🔴' if level == 'critical' else '🟠'} {level.capitalize()} risk: {district}",
                        message=(
                            f"District '{district}' has reached {level} risk level "
                            f"(score: {score:.0f}/100). "
                            f"Recent activity: {data.get('components', {}).get('recent_7d', '?')} crimes in last 7 days. "
                            f"Recommend increasing patrol frequency."
                        ),
                        alert_type="high_risk",
                        severity=level,
                        district=district,
                    )
                    await db.commit()

                    # Publish to WebSocket channel
                    await redis.publish(
                        "alerts:broadcast",
                        json.dumps({
                            "type": "new_alert",
                            "alert_id": str(alert.id),
                            "severity": level,
                            "title": alert.title,
                        }),
                    )

                    # Prevent duplicate alerts for 2 hours
                    await redis.setex(cache_key, 7200, "1")
                    alerts_fired += 1

            logger.info("alert_check_complete", alerts_fired=alerts_fired)
            return {"status": "complete", "alerts_fired": alerts_fired}

        finally:
            await db.close()
            await engine.dispose()

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("alert_check_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}
