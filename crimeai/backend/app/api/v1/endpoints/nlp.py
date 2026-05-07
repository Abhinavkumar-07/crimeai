"""
NLP endpoints — full implementation replacing Step 2 stub.
Covers inline text extraction, FIR reprocessing, and similarity search.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, require_role
from app.core.config import settings
from app.core.security import UserRole
from app.db.redis import get_redis
from app.db.session import get_db
from app.services.nlp_service import NLPService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _get_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> NLPService:
    return NLPService(db=db, redis=redis)


# ── Request schemas ────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=20, max_length=10000,
                      description="Raw FIR text or any crime-related text to analyse")


class SimilarityRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)
    crime_type: str | None = Field(None, description="Optional filter: only search within this crime type")
    min_similarity: float = Field(default=0.5, ge=0.0, le=1.0)


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=5000)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/extract",
    summary="Extract entities from text (location, crime type, weapon, suspects)",
)
@limiter.limit(settings.RATE_LIMIT_ML)
async def extract_entities(
    request: Request,
    body: ExtractRequest,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    service: Annotated[NLPService, Depends(_get_service)],
) -> dict:
    """
    Runs the full spaCy + rule-based NLP pipeline on the provided text.

    Returns:
    - **locations**: all detected locations (GPE, LOC, FAC entities + patterns)
    - **crime_type**: detected crime category
    - **weapons**: weapon mentions
    - **suspects**: structured physical descriptions of accused persons
    - **time_references**: temporal expressions
    - **ipc_sections**: Indian Penal Code sections mentioned
    - **overall_confidence**: 0–1 score based on entities found
    """
    return await service.extract_inline(body.text)


@router.post(
    "/similarity",
    summary="Find crimes similar to text using pgvector embeddings",
)
async def find_similar_crimes(
    body: SimilarityRequest,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))],
    service: Annotated[NLPService, Depends(_get_service)],
) -> dict:
    """
    Encodes query text with sentence-transformers (all-MiniLM-L6-v2, 384-dim)
    and searches pgvector for the most similar crime records.

    Requires crimes to have embeddings populated (POST /api/v1/ml/embed-crimes).
    """
    results = await service.find_similar_crimes(
        query_text=body.text,
        top_k=body.top_k,
        crime_type_filter=body.crime_type,
        min_similarity=body.min_similarity,
    )
    return {
        "query": body.text[:100],
        "top_k": body.top_k,
        "min_similarity": body.min_similarity,
        "results": results,
        "total_found": len(results),
    }


@router.post(
    "/classify",
    summary="Classify crime type from free-form text",
)
async def classify_crime(
    body: ClassifyRequest,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
) -> dict:
    """
    Two-layer classification: keyword matching first, then
    zero-shot HuggingFace model as fallback for ambiguous cases.
    """
    from app.nlp.parsers.crime_classifier import classify_crime_type
    result = classify_crime_type(text=body.text)
    return {
        "crime_type": result["crime_type"],
        "confidence": result["confidence"],
        "method": result["method"],
        "top_predictions": result["keyword_predictions"],
    }


@router.get(
    "/pending",
    summary="List FIRs pending NLP processing (Admin)",
)
async def get_pending_firs(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    service: Annotated[NLPService, Depends(_get_service)],
) -> dict:
    """Returns FIRs with nlp_status='pending'. Useful for monitoring the queue."""
    pending = await service.get_pending_firs()
    return {"total": len(pending), "items": pending}


@router.post(
    "/process-pending",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue all pending FIRs for NLP processing (Admin)",
)
async def process_pending_firs(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    service: Annotated[NLPService, Depends(_get_service)],
) -> dict:
    """
    Dispatches a Celery task to process all FIRs in 'pending' state.
    Useful for recovery after worker downtime.
    """
    from app.workers.tasks.nlp_tasks import process_pending_firs as task
    t = task.apply_async(queue="nlp")
    return {
        "message": "Pending FIR processing queued",
        "task_id": t.id,
        "status_url": f"/api/v1/ml/tasks/{t.id}",
    }
