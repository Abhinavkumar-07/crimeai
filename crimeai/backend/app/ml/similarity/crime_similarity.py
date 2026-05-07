"""
Crime Similarity Search
------------------------
Wraps the pgvector similarity search via SQLAlchemy raw SQL.
The crimes table has an 'embedding' column (float array) that
is populated by the batch embedding job.

Also provides in-memory cosine similarity fallback when
pgvector is not available (dev/test).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MLServiceError
from app.core.logging import get_logger
from app.ml.similarity.embeddings import embed_text

logger = get_logger(__name__)


async def find_similar_crimes(
    db: AsyncSession,
    query_text: str,
    top_k: int = 5,
    crime_type_filter: str | None = None,
    min_similarity: float = 0.5,
) -> list[dict]:
    """
    Find the top-K crimes most similar to query_text using pgvector.

    Uses cosine distance (<=> operator) which pgvector supports
    natively with an IVFFLAT index.

    Returns list of {id, crime_type, description, district, similarity, occurred_at}
    """
    query_vector = embed_text(query_text)
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

    # Build SQL using pgvector's cosine distance operator
    # 1 - cosine_distance = cosine_similarity
    sql_parts = [
        "SELECT",
        "  id::text,",
        "  crime_type,",
        "  sub_type,",
        "  description,",
        "  district,",
        "  city,",
        "  severity,",
        "  occurred_at,",
        "  case_number,",
        "  1 - (embedding::vector <=> :query_vector::vector) AS similarity",
        "FROM crimes",
        "WHERE embedding IS NOT NULL",
    ]

    params: dict[str, Any] = {
        "query_vector": vector_str,
        "min_similarity": min_similarity,
        "top_k": top_k,
    }

    if crime_type_filter:
        sql_parts.append("  AND crime_type = :crime_type")
        params["crime_type"] = crime_type_filter

    sql_parts += [
        "  AND 1 - (embedding::vector <=> :query_vector::vector) >= :min_similarity",
        "ORDER BY embedding::vector <=> :query_vector::vector",
        "LIMIT :top_k",
    ]

    sql = "\n".join(sql_parts)

    try:
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
    except Exception as exc:
        # pgvector not available or embedding column missing
        logger.warning("pgvector_query_failed", error=str(exc))
        raise MLServiceError(
            "Vector similarity search unavailable",
            detail={"hint": "Ensure pgvector extension and crime embeddings are populated"},
        ) from exc

    return [
        {
            "id": row.id,
            "crime_type": row.crime_type,
            "sub_type": row.sub_type,
            "description": (row.description or "")[:300],
            "district": row.district,
            "city": row.city,
            "severity": row.severity,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "case_number": row.case_number,
            "similarity": round(float(row.similarity), 4),
        }
        for row in rows
    ]


async def batch_embed_crimes(
    db: AsyncSession,
    limit: int = 1000,
) -> dict[str, int]:
    """
    Embed all crimes that don't have an embedding yet.
    Called by the Celery batch job.

    Returns {"processed": N, "skipped": M, "errors": K}
    """
    from app.ml.similarity.embeddings import embed_batch

    # Fetch crimes without embeddings
    sql = text("""
        SELECT id::text, crime_type, sub_type, description, district
        FROM crimes
        WHERE embedding IS NULL
        LIMIT :limit
    """)
    result = await db.execute(sql, {"limit": limit})
    rows = result.fetchall()

    if not rows:
        return {"processed": 0, "skipped": 0, "errors": 0}

    # Build text for each crime (combine type + description)
    texts = []
    ids = []
    for row in rows:
        parts = [row.crime_type]
        if row.sub_type:
            parts.append(row.sub_type)
        if row.description:
            parts.append(row.description)
        if row.district:
            parts.append(f"in {row.district}")
        texts.append(" ".join(parts))
        ids.append(row.id)

    # Embed batch
    try:
        vectors = embed_batch(texts)
    except MLServiceError as exc:
        logger.error("batch_embed_failed", error=str(exc))
        return {"processed": 0, "skipped": len(rows), "errors": len(rows)}

    # Write back to DB
    processed = 0
    errors = 0
    for crime_id, vector in zip(ids, vectors):
        vector_str = "[" + ",".join(str(v) for v in vector) + "]"
        try:
            await db.execute(
                text("UPDATE crimes SET embedding = :vec::vector WHERE id = :id::uuid"),
                {"vec": vector_str, "id": crime_id},
            )
            processed += 1
        except Exception as exc:
            logger.warning("crime_embed_update_failed", crime_id=crime_id, error=str(exc))
            errors += 1

    await db.commit()
    logger.info("batch_embed_complete", processed=processed, errors=errors)
    return {"processed": processed, "skipped": 0, "errors": errors}


async def create_pgvector_index(db: AsyncSession) -> None:
    """
    Create IVFFlat index on the embedding column for fast similarity search.
    Run once after batch embedding is complete.
    num_lists = sqrt(N) is a good heuristic.
    """
    try:
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_crimes_embedding_ivfflat
            ON crimes
            USING ivfflat (embedding::vector vector_cosine_ops)
            WITH (lists = 100)
        """))
        await db.commit()
        logger.info("pgvector_index_created")
    except Exception as exc:
        logger.warning("pgvector_index_creation_failed", error=str(exc))
