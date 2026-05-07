"""
ML package — exposes the main service class and key functions.
"""
from app.ml.clustering.dbscan import ClusterResult, run_dbscan, find_optimal_eps
from app.ml.prediction.hotspot_predictor import (
    train_hotspot_model,
    predict_hotspots,
    predict_next_24h,
    get_model_metadata,
)
from app.ml.prediction.risk_scorer import (
    compute_district_risk_scores,
    get_cached_risk_scores,
    score_single_crime,
)
from app.ml.prediction.suspect_profiler import build_area_profile
from app.ml.similarity.embeddings import embed_text, embed_batch
from app.ml.similarity.crime_similarity import find_similar_crimes, batch_embed_crimes

__all__ = [
    "ClusterResult",
    "run_dbscan",
    "find_optimal_eps",
    "train_hotspot_model",
    "predict_hotspots",
    "predict_next_24h",
    "get_model_metadata",
    "compute_district_risk_scores",
    "get_cached_risk_scores",
    "score_single_crime",
    "build_area_profile",
    "embed_text",
    "embed_batch",
    "find_similar_crimes",
    "batch_embed_crimes",
]
