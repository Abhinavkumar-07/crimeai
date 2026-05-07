"""
NLP Service — orchestration layer between endpoints/workers and NLP modules.
Handles DB I/O, caching, and result persistence.
"""
from __future__ import annotations

import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NLPServiceError, NotFoundError
from app.core.logging import get_logger
from app.db.redis import CacheManager
from app.nlp.parsers.fir_pipeline import process_fir_text
from app.repositories.fir_repository import FIRRepository
from app.ml.similarity.crime_similarity import find_similar_crimes

logger = get_logger(__name__)


class NLPService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.fir_repo = FIRRepository(db)
        self.cache = CacheManager(redis, namespace="nlp")

    async def process_fir(self, fir_id: uuid.UUID) -> dict[str, Any]:
        """
        Run NLP pipeline on a stored FIR and persist results to DB.
        Called by the Celery worker and the /reprocess endpoint.
        """
        fir = await self.fir_repo.get_by_id(fir_id)
        if not fir:
            raise NotFoundError(f"FIR {fir_id} not found")

        # Mark as processing
        await self.fir_repo.set_nlp_status(fir_id, "processing")

        try:
            result = process_fir_text(
                text=fir.raw_text,
                fir_number=fir.fir_number,
            )
            confidence = result.get("overall_confidence", 0.0)

            await self.fir_repo.update_nlp_result(
                fir_id=fir_id,
                entities=result,
                confidence=confidence,
                status="completed",
            )

            # Invalidate any cached FIR data
            await self.cache.delete(f"fir:{fir_id}")

            logger.info(
                "fir_nlp_persisted",
                fir_id=str(fir_id),
                crime_type=result.get("crime_type"),
                confidence=confidence,
            )
            return result

        except NLPServiceError:
            await self.fir_repo.set_nlp_status(fir_id, "failed")
            raise
        except Exception as exc:
            await self.fir_repo.set_nlp_status(fir_id, "failed")
            raise NLPServiceError(
                "NLP pipeline failed unexpectedly",
                detail={"fir_id": str(fir_id), "error": str(exc)},
            ) from exc

    async def extract_inline(self, text: str) -> dict[str, Any]:
        """
        Run NLP on raw text without persisting to DB.
        Used by the /nlp/extract endpoint for quick analysis.
        """
        # Cache based on text hash (avoid re-processing identical texts)
        import hashlib
        cache_key = f"extract:{hashlib.md5(text.encode()).hexdigest()}"
        cached = await self.cache.get(cache_key)
        if cached:
            return {**cached, "from_cache": True}

        result = process_fir_text(text=text)
        await self.cache.set(cache_key, result, ttl=300)
        return result

    async def find_similar_crimes(
        self,
        query_text: str,
        top_k: int = 5,
        crime_type_filter: str | None = None,
        min_similarity: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Find crimes similar to query text using pgvector."""
        return await find_similar_crimes(
            db=self.db,
            query_text=query_text,
            top_k=top_k,
            crime_type_filter=crime_type_filter,
            min_similarity=min_similarity,
        )

    async def get_pending_firs(self) -> list[dict[str, Any]]:
        """Return FIRs that haven't been NLP-processed yet."""
        firs, total = await self.fir_repo.list_firs(nlp_status="pending", limit=100)
        return [
            {"fir_id": str(f.id), "fir_number": f.fir_number, "created_at": f.created_at.isoformat()}
            for f in firs
        ]
