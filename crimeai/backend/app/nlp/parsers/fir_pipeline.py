"""
FIR Processing Pipeline
------------------------
Orchestrates the full NLP pipeline for a single FIR document:

  1. Preprocess text (clean, expand abbreviations)
  2. Entity extraction (spaCy NER + rule-based)
  3. Crime type classification (keyword → zero-shot fallback)
  4. Severity inference
  5. Structure and return results

This is the main entry point called by the Celery NLP worker.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import NLPServiceError
from app.core.logging import get_logger
from app.nlp.parsers.crime_classifier import classify_crime_type, classify_severity
from app.nlp.parsers.entity_extractor import ExtractedEntities, extract_entities

logger = get_logger(__name__)


def process_fir_text(
    text: str,
    fir_number: str | None = None,
) -> dict[str, Any]:
    """
    Full FIR NLP pipeline. Returns a structured dict ready to be
    stored in the fir_reports.extracted_entities JSONB column.

    Raises NLPServiceError on unrecoverable failures.
    """
    if not text or len(text.strip()) < 20:
        raise NLPServiceError(
            "FIR text too short for processing",
            detail={"min_length": 20, "actual_length": len(text)},
        )

    logger.info(
        "fir_pipeline_started",
        fir_number=fir_number,
        text_length=len(text),
    )

    # ── Step 1: Entity extraction ─────────────────────────────────────────────
    try:
        entities: ExtractedEntities = extract_entities(text)
    except NLPServiceError:
        raise
    except Exception as exc:
        raise NLPServiceError(
            "Entity extraction failed",
            detail={"error": str(exc)},
        ) from exc

    # ── Step 2: Crime type classification ─────────────────────────────────────
    classification = classify_crime_type(
        text=text,
        keyword_crime_type=entities.crime_type,
        keyword_confidence=entities.crime_type_confidence,
    )

    # Merge classification back into entities if it found a better result
    if classification["confidence"] > entities.crime_type_confidence:
        entities.crime_type = classification["crime_type"]
        entities.crime_type_confidence = classification["confidence"]

    # ── Step 3: Severity inference ────────────────────────────────────────────
    inferred_severity = classify_severity(
        crime_type=entities.crime_type or "other",
        has_weapon=len(entities.weapons) > 0,
        has_injury=_text_mentions_injury(text),
        num_suspects=len(entities.suspects),
        text=text,
    )

    # ── Step 4: Build output structure ───────────────────────────────────────
    result = {
        # Core extracted fields
        "locations": entities.locations,
        "primary_location": entities.locations[0] if entities.locations else None,
        "crime_type": entities.crime_type,
        "crime_type_confidence": round(entities.crime_type_confidence, 3),
        "weapons": entities.weapons,
        "suspects": entities.suspects,
        "time_references": entities.time_references,
        "vehicles": entities.vehicles,
        "ipc_sections": entities.ipc_sections,
        "persons_mentioned": entities.persons_mentioned,

        # Classification details
        "classification": {
            "method": classification["method"],
            "confidence": classification["confidence"],
            "top_predictions": classification["keyword_predictions"],
        },

        # Inferred attributes
        "inferred_severity": inferred_severity,
        "has_weapon": len(entities.weapons) > 0,
        "has_injury": _text_mentions_injury(text),
        "num_suspects": len(entities.suspects),

        # Metadata
        "overall_confidence": round(entities.overall_confidence, 3),
        "processing_notes": entities.processing_notes,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "fir_number": fir_number,
        "text_length": len(text),
        "pipeline_version": "1.0.0",
    }

    logger.info(
        "fir_pipeline_complete",
        fir_number=fir_number,
        crime_type=entities.crime_type,
        n_locations=len(entities.locations),
        n_weapons=len(entities.weapons),
        n_suspects=len(entities.suspects),
        confidence=entities.overall_confidence,
    )

    return result


def _text_mentions_injury(text: str) -> bool:
    """Detect if text describes injury or physical harm."""
    text_lower = text.lower()
    injury_keywords = [
        "injured", "injury", "hurt", "wound", "wounded", "bleeding",
        "fracture", "broken bone", "hospitalised", "hospital", "critical",
        "grievous hurt", "bodily harm", "medical treatment", "first aid",
        "unconscious", "dead", "death", "deceased",
    ]
    return any(kw in text_lower for kw in injury_keywords)


def batch_process_firs(
    fir_records: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    Process multiple FIR records in sequence.
    Each record: {"fir_id": str, "fir_number": str, "text": str}
    Returns list of {fir_id, result | error}
    """
    results = []
    for record in fir_records:
        fir_id = record.get("fir_id", "unknown")
        try:
            result = process_fir_text(
                text=record["text"],
                fir_number=record.get("fir_number"),
            )
            results.append({"fir_id": fir_id, "status": "success", "result": result})
        except NLPServiceError as exc:
            logger.warning("fir_batch_item_failed", fir_id=fir_id, error=exc.message)
            results.append({
                "fir_id": fir_id,
                "status": "error",
                "error": exc.message,
            })
        except Exception as exc:
            logger.error("fir_batch_item_unexpected_error", fir_id=fir_id, error=str(exc))
            results.append({
                "fir_id": fir_id,
                "status": "error",
                "error": str(exc),
            })
    return results
