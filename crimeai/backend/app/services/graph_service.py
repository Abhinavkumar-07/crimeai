"""
Graph Service — orchestration between endpoints and graph algorithms.
Fetches crime data from DB, runs graph algorithms, caches results.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MLServiceError, NotFoundError
from app.core.logging import get_logger
from app.db.redis import CacheManager
from app.graph.algorithms.escape_analyzer import analyze_escape_routes
from app.graph.algorithms.patrol_optimizer import optimize_patrol
from app.graph.algorithms.simulation_engine import list_scenarios, run_simulation
from app.ml.prediction.risk_scorer import get_cached_risk_scores

logger = get_logger(__name__)


class GraphService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.cache = CacheManager(redis, namespace="graph")

    async def _fetch_crime_records(
        self,
        district: str | None = None,
        lookback_days: int = 60,
    ) -> list[dict]:
        """Fetch crime records from DB for graph computations."""
        from app.models.crime import Crime
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        query = select(
            Crime.id, Crime.district, Crime.crime_type,
            Crime.severity, Crime.latitude, Crime.longitude,
            Crime.risk_score, Crime.occurred_at,
        ).where(Crime.occurred_at >= cutoff)
        if district:
            query = query.where(Crime.district == district)

        result = await self.db.execute(query)
        return [
            {
                "id": str(r.id),
                "district": r.district or "Unknown",
                "crime_type": r.crime_type,
                "severity": r.severity,
                "lat": float(r.latitude),
                "lng": float(r.longitude),
                "risk_score": float(r.risk_score or 0),
                "occurred_at": r.occurred_at.isoformat(),
            }
            for r in result.all()
        ]

    async def _build_checkpoints_from_crimes(
        self, crimes: list[dict], num_checkpoints: int = 10
    ) -> list[dict]:
        """
        Aggregate crime locations into checkpoint clusters.
        Uses grid-based clustering to avoid passing 500+ raw crime points.
        """
        if not crimes:
            return []

        # Group by 0.01° grid cells (~1.1km)
        grid: dict[tuple, list[dict]] = {}
        for c in crimes:
            cell = (round(c["lat"] / 0.01) * 0.01, round(c["lng"] / 0.01) * 0.01)
            grid.setdefault(cell, []).append(c)

        # Take top-N cells by crime count
        sorted_cells = sorted(grid.items(), key=lambda x: len(x[1]), reverse=True)
        checkpoints = []
        for i, ((cell_lat, cell_lng), cell_crimes) in enumerate(sorted_cells[:num_checkpoints]):
            avg_risk = sum(c.get("risk_score", 0) for c in cell_crimes) / len(cell_crimes)
            checkpoints.append({
                "id": f"CP-{i:03d}",
                "lat": cell_lat,
                "lng": cell_lng,
                "label": f"Hotspot {i + 1}",
                "crime_count": len(cell_crimes),
                "risk_score": avg_risk,
                "node_type": "checkpoint",
                "district": cell_crimes[0].get("district", ""),
            })
        return checkpoints

    # ── Patrol optimization ───────────────────────────────────────────────────

    async def optimize_patrol_route(
        self,
        start_lat: float,
        start_lng: float,
        district: str,
        strategy: str = "risk_weighted",
        num_checkpoints: int = 5,
        patrol_type: str = "vehicle",
    ) -> dict:
        cache_key = f"patrol:{district}:{strategy}:{num_checkpoints}"
        cached = await self.cache.get(cache_key)
        if cached:
            return {**cached, "from_cache": True}

        crimes = await self._fetch_crime_records(district=district, lookback_days=90)
        checkpoints = await self._build_checkpoints_from_crimes(
            crimes, num_checkpoints=num_checkpoints * 3  # oversample then filter
        )
        risk_scores = get_cached_risk_scores()
        district_risk = {district: risk_scores.get(district, {}).get("score", 30.0)}

        route = optimize_patrol(
            start_lat=start_lat,
            start_lng=start_lng,
            district=district,
            checkpoints=checkpoints,
            strategy=strategy,
            num_checkpoints=num_checkpoints,
            patrol_type=patrol_type,
            risk_scores=district_risk,
        )
        result = route.to_dict()
        await self.cache.set(cache_key, result, ttl=900)   # 15 min cache
        return result

    # ── Escape analysis ───────────────────────────────────────────────────────

    async def analyze_escape(
        self,
        crime_lat: float,
        crime_lng: float,
        district: str,
        search_radius_km: float = 5.0,
        num_routes: int = 3,
    ) -> dict:
        from app.repositories.crime_repository import CrimeRepository
        repo = CrimeRepository(self.db)
        nearby_crimes = await repo.find_within_radius(
            latitude=crime_lat,
            longitude=crime_lng,
            radius_km=search_radius_km,
            limit=50,
        )
        nearby_dicts = [
            {"lat": float(c.latitude), "lng": float(c.longitude), "district": c.district}
            for c in nearby_crimes
        ]
        risk_scores_raw = get_cached_risk_scores()
        risk_scores = {d: v.get("score", 30.0) for d, v in risk_scores_raw.items()}

        analysis = analyze_escape_routes(
            crime_lat=crime_lat,
            crime_lng=crime_lng,
            district=district,
            nearby_crimes=nearby_dicts,
            risk_scores=risk_scores,
            search_radius_km=search_radius_km,
            num_routes=num_routes,
        )
        return analysis.to_dict()

    # ── Simulation ────────────────────────────────────────────────────────────

    async def run_what_if(
        self,
        scenario: str,
        district: str,
        parameters: dict,
        num_simulations: int = 200,
    ) -> dict:
        crimes = await self._fetch_crime_records(district=district, lookback_days=60)
        if not crimes:
            return {
                "status": "insufficient_data",
                "message": f"No crime data found for district '{district}'",
            }

        result = run_simulation(
            scenario=scenario,
            district=district,
            parameters=parameters,
            crime_history=crimes,
            num_simulations=num_simulations,
        )
        return result.to_dict()

    async def get_scenario_list(self) -> list[dict]:
        return list_scenarios()
