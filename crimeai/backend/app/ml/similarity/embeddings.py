"""
Crime Similarity Engine
------------------------
Uses sentence-transformers to embed crime descriptions into dense vectors,
then stores them in PostgreSQL via the pgvector extension.

Supports:
  - Batch embedding of all crimes (run once / on schedule)
  - Single-query similarity search (cosine distance via pgvector)
  - Top-K similar crime retrieval
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import numpy as np

from app.core.exceptions import MLServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Model name — all-MiniLM-L6-v2 is fast (80ms/doc) and good quality (384-dim)
_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_EMBEDDING_DIM = 384

# Lazy-loaded model singleton
_model = None


def _get_model():
    """Lazily load the sentence-transformer model (only once per process)."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("embedding_model_loading", model=_EMBEDDING_MODEL)
            _model = SentenceTransformer(_EMBEDDING_MODEL)
            logger.info("embedding_model_ready", model=_EMBEDDING_MODEL, dim=_EMBEDDING_DIM)
        except ImportError as exc:
            raise MLServiceError(
                "sentence-transformers not installed",
                detail={"hint": "pip install sentence-transformers"},
            ) from exc
        except Exception as exc:
            raise MLServiceError(f"Failed to load embedding model: {exc}") from exc
    return _model


def embed_text(text: str) -> list[float]:
    """
    Embed a single text string into a 384-dim vector.
    Returns a plain Python list (JSON-serialisable, pgvector-compatible).
    """
    model = _get_model()
    text = _preprocess_text(text)
    try:
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception as exc:
        raise MLServiceError(f"Embedding failed: {exc}") from exc


def embed_batch(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """
    Embed multiple texts efficiently in batches.
    Returns list of 384-dim vectors.
    """
    model = _get_model()
    processed = [_preprocess_text(t) for t in texts]
    try:
        vectors = model.encode(
            processed,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 100,
        )
        logger.info("batch_embedding_complete", n_texts=len(texts))
        return [v.tolist() for v in vectors]
    except Exception as exc:
        raise MLServiceError(f"Batch embedding failed: {exc}") from exc


def _preprocess_text(text: str) -> str:
    """Clean and truncate text before embedding."""
    if not text:
        return "unknown crime incident"
    # Truncate to 512 chars (model max token limit ~256 tokens ≈ 512 chars)
    text = text.strip()[:512]
    return text


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.array(vec_a)
    b = np.array(vec_b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
