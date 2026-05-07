"""NLP package — public exports."""
from app.nlp.parsers.entity_extractor import extract_entities, ExtractedEntities
from app.nlp.parsers.crime_classifier import classify_crime_type, classify_severity
from app.nlp.parsers.fir_pipeline import process_fir_text, batch_process_firs

__all__ = [
    "extract_entities",
    "ExtractedEntities",
    "classify_crime_type",
    "classify_severity",
    "process_fir_text",
    "batch_process_firs",
]
