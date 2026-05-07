"""
ML Service — orchestration layer between endpoints/workers and ML modules.
Handles DB I/O, caching, and result persistence.
All heavy computation is delegated to the pure ML modules.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MLServiceError
from app.core.logging import get_logger
from app.db.redis import CacheManager
from app.ml.clustering.dbscan import ClusterResult, find_optimal_eps, run_dbscan
from app.ml.prediction.hotspot_predictor import (
    get_model_metadata,
    predict_hotspots,
    predict_next_24h,
    train_hotspot_model,
)
from app.ml.prediction.risk_scorer import (
    compute_district_risk_scores,
    get_cached_risk_scores,
)
from app.ml.prediction.suspect_profiler import build_area_profile
from app.ml.similarity.crime_similarity import (
    batch_embed_crimes,
    find_similar_crimes,
)
from app.repositories.crime_repository import CrimeRepository

logger = get_logger(__name__)

_CLUSTER_CACHE_KEY = "ml:clusters:latest"
_RISK_MAP_CACHE_KEY = "ml:risk_map"
_HOTSPOT_24H_KEY = "ml:hotspot_24h"
_CACHE_TTL_CLUSTERS = 3600     # 1 hour
_CACHE_TTL_RISK = 1800         # 30 min
_CACHE_TTL_HOTSPOT = 900       # 15 min


class MLService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.repo = CrimeRepository(db)
        self.cache = CacheManager(redis, namespace="ml")

    # ── Clustering ────────────────────────────────────────────────────────────

    async def run_clustering(
        self,
        eps_km: float | None = None,
        min_samples: int | None = None,
        from_date: datetime | None = None,
        auto_eps: bool = False,
    ) -> dict[str, Any]:
        """
        Full clustering pipeline:
        1. Fetch all crime coordinates from DB
        2. Optionally find optimal eps via k-distance elbow
        3. Run DBSCAN
        4. Write cluster_id back to each crime row
        5. Cache cluster summaries in Redis
        """
        from_date = from_date or (datetime.now(timezone.utc) - timedelta(days=365))

        logger.info("clustering_started", from_date=from_date.isoformat())

        crime_records = await self.repo.get_all_coordinates(from_date=from_date)
        if len(crime_records) < 3:
            return {
                "status": "insufficient_data",
                "n_records": len(crime_records),
                "message": "At least 3 crime records needed for clustering",
            }

        # Auto-detect eps if requested
        if auto_eps:
            eps_km = find_optimal_eps(crime_records, min_samples=min_samples or 3)
            logger.info("auto_eps_selected", eps_km=eps_km)

        # Run DBSCAN
        result: ClusterResult = run_dbscan(
            crime_records=crime_records,
            eps_km=eps_km,
            min_samples=min_samples,
        )

        # Persist cluster assignments to DB
        updated = await self.repo.bulk_update_clusters(result.assignments)

        # Cache cluster summaries
        cache_payload = {
            "num_clusters": result.num_clusters,
            "noise_points": result.noise_points,
            "total_points": result.total_points,
            "coverage_pct": result.coverage_pct,
            "parameters": result.parameters,
            "clusters": result.cluster_summaries,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.cache.set(_CLUSTER_CACHE_KEY, cache_payload, ttl=_CACHE_TTL_CLUSTERS)

        logger.info(
            "clustering_complete",
            n_clusters=result.num_clusters,
            n_noise=result.noise_points,
            db_updated=updated,
        )

        return {
            "status": "complete",
            "n_clusters": result.num_clusters,
            "noise_points": result.noise_points,
            "total_points": result.total_points,
            "coverage_pct": result.coverage_pct,
            "parameters": result.parameters,
            "clusters": result.cluster_summaries,
        }

    async def get_clusters(self) -> dict[str, Any]:
        """Return cached clustering results."""
        cached = await self.cache.get(_CLUSTER_CACHE_KEY)
        if cached:
            return {**cached, "from_cache": True}
        return {
            "status": "not_run",
            "message": "No clustering results yet. POST /api/v1/ml/cluster to run.",
            "from_cache": False,
        }

    # ── Hotspot prediction ────────────────────────────────────────────────────

    async def train_and_predict_hotspots(self) -> dict[str, Any]:
        """
        Full hotspot pipeline:
        1. Fetch all crime records for training
        2. Train Random Forest model
        3. Predict next 24h for all known districts
        4. Cache results
        """
        crime_records = await self.repo.get_all_coordinates()
        if len(crime_records) < 50:
            return {
                "status": "insufficient_data",
                "n_records": len(crime_records),
                "message": "At least 50 crime records needed for hotspot training",
            }

        # Also need severity + occurred_at for training
        from sqlalchemy import select
        from app.models.crime import Crime
        full_rows = await self.db.execute(
            select(
                Crime.id,
                Crime.district,
                Crime.crime_type,
                Crime.severity,
                Crime.occurred_at,
                Crime.latitude,
                Crime.longitude,
            )
        )
        records = [
            {
                "id": str(r.id),
                "district": r.district or "Unknown",
                "crime_type": r.crime_type,
                "severity": r.severity,
                "occurred_at": r.occurred_at.isoformat(),
                "lat": float(r.latitude),
                "lng": float(r.longitude),
            }
            for r in full_rows.all()
        ]

        # Train model
        try:
            training_result = train_hotspot_model(records)
        except MLServiceError as exc:
            return {"status": "training_failed", "error": exc.message}

        # Get unique districts
        districts = list({r["district"] for r in records if r["district"] != "Unknown"})

        # Predict next 24h
        predictions_24h = predict_next_24h(districts)

        # Compute risk map
        risk_scores = compute_district_risk_scores(records)

        # Cache everything
        await self.cache.set(
            _HOTSPOT_24H_KEY,
            predictions_24h,
            ttl=_CACHE_TTL_HOTSPOT,
        )
        await self.cache.set(
            _RISK_MAP_CACHE_KEY,
            risk_scores,
            ttl=_CACHE_TTL_RISK,
        )

        # Update DB risk scores per crime
        risk_score_updates = [
            {"id": r["id"], "risk_score": risk_scores.get(r["district"], {}).get("score", 0.0)}
            for r in records
        ]
        await self.repo.bulk_update_risk_scores(risk_score_updates)

        return {
            "status": "complete",
            "training": {
                "accuracy": training_result.accuracy,
                "auc_roc": training_result.auc_roc,
                "n_samples": training_result.n_training_samples,
                "trained_at": training_result.trained_at,
            },
            "n_districts": len(districts),
            "predictions_24h": predictions_24h[:3],   # Preview first 3 hours
            "risk_map_districts": len(risk_scores),
        }

    async def get_hotspot_predictions(self) -> dict[str, Any]:
        """Return cached 24-hour hotspot predictions."""
        cached = await self.cache.get(_HOTSPOT_24H_KEY)
        if cached:
            return {"status": "ok", "predictions": cached, "from_cache": True}
        return {
            "status": "not_run",
            "predictions": [],
            "from_cache": False,
            "message": "POST /api/v1/ml/hotspot-prediction to generate predictions",
        }

    async def get_risk_map(self) -> dict[str, Any]:
        """Return cached district risk scores."""
        cached = await self.cache.get(_RISK_MAP_CACHE_KEY)
        if cached:
            return {"risk_map": cached, "from_cache": True}
        # Fall back to disk cache
        disk_cache = get_cached_risk_scores()
        if disk_cache:
            return {"risk_map": disk_cache, "from_cache": True, "source": "disk"}
        return {
            "risk_map": {},
            "from_cache": False,
            "message": "POST /api/v1/ml/hotspot-prediction to compute risk map",
        }

    # ── Similarity search ─────────────────────────────────────────────────────

    async def find_similar(
        self,
        query_text: str,
        top_k: int = 5,
        crime_type_filter: str | None = None,
        min_similarity: float = 0.5,
    ) -> list[dict]:
        return await find_similar_crimes(
            db=self.db,
            query_text=query_text,
            top_k=top_k,
            crime_type_filter=crime_type_filter,
            min_similarity=min_similarity,
        )

    async def run_batch_embedding(self, limit: int = 1000) -> dict[str, int]:
        """Embed all un-embedded crimes. Called by Celery worker."""
        return await batch_embed_crimes(self.db, limit=limit)

    # ── Area profile ──────────────────────────────────────────────────────────

    async def get_area_profile(
        self, district: str, lookback_days: int = 60
    ) -> dict[str, Any]:
        cache_key = f"profile:{district}:{lookback_days}"
        cached = await self.cache.get(cache_key)
        if cached:
            return {**cached, "from_cache": True}

        from sqlalchemy import select
        from app.models.crime import Crime
        rows = await self.db.execute(
            select(
                Crime.id,
                Crime.district,
                Crime.crime_type,
                Crime.sub_type,
                Crime.severity,
                Crime.occurred_at,
                Crime.latitude,
                Crime.longitude,
            ).where(Crime.district == district)
        )
        records = [
            {
                "id": str(r.id),
                "district": r.district or district,
                "crime_type": r.crime_type,
                "sub_type": r.sub_type,
                "severity": r.severity,
                "occurred_at": r.occurred_at.isoformat(),
                "latitude": float(r.latitude),
                "longitude": float(r.longitude),
            }
            for r in rows.all()
        ]

        profile = build_area_profile(records, district=district, lookback_days=lookback_days)
        await self.cache.set(cache_key, profile, ttl=1800)
        return profile

    async def get_model_info(self) -> dict[str, Any]:
        return {
            "hotspot_model": get_model_metadata(),
            "embedding_model": "all-MiniLM-L6-v2 (384-dim)",
        }
