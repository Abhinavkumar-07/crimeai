"""
Area Risk Scoring Module
-------------------------
Computes a composite risk score (0–100) for each district based on:
  1. Crime frequency (normalised count)
  2. Crime severity (weighted average)
  3. Crime type danger weights
  4. Recency bias (recent crimes score higher)
  5. Time-of-day patterns (is the area active at dangerous hours?)

Optionally trains an XGBoost regression model when enough data
is available for a more sophisticated prediction.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

_MODEL_DIR = Path(__file__).parent / "saved"
_RISK_SCORES_PATH = _MODEL_DIR / "risk_scores.json"


# Danger weights per crime type (tunable by analysts)
_CRIME_DANGER_WEIGHTS: dict[str, float] = {
    "murder":          10.0,
    "kidnapping":      9.0,
    "sexual_offense":  9.0,
    "armed_robbery":   8.5,
    "robbery":         7.0,
    "assault":         6.5,
    "extortion":       6.0,
    "arson":           5.5,
    "drug_offense":    5.0,
    "fraud":           4.0,
    "theft":           3.5,
    "vandalism":       2.0,
    "trespass":        1.5,
    "traffic_violation": 1.0,
    "cybercrime":      3.0,
    "other":           2.0,
}

_DEFAULT_DANGER_WEIGHT = 2.5


def compute_district_risk_scores(
    crime_records: list[dict],
    lookback_days: int = 90,
) -> dict[str, dict]:
    """
    Compute risk scores for all districts present in crime_records.

    crime_records: list of dicts with keys:
        id, district, crime_type, severity, occurred_at (ISO string or datetime)

    Returns: {district_name: {"score": float, "level": str, "components": dict}}
    """
    if not crime_records:
        return {}

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(crime_records)
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True)
    df["district"] = df["district"].fillna("Unknown")

    # Filter to lookback window
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    df = df[df["occurred_at"] >= cutoff].copy()

    if df.empty:
        return {}

    # Add danger weight per crime type
    df["danger_weight"] = df["crime_type"].map(_CRIME_DANGER_WEIGHTS).fillna(_DEFAULT_DANGER_WEIGHT)

    # Recency weight: crimes in last 7 days get weight 3x, last 30 days 2x, older 1x
    now = datetime.now(timezone.utc)
    df["days_ago"] = (now - df["occurred_at"]).dt.total_seconds() / 86400
    df["recency_weight"] = np.where(
        df["days_ago"] <= 7, 3.0,
        np.where(df["days_ago"] <= 30, 2.0, 1.0)
    )

    # Composite weight per crime
    df["composite_weight"] = (
        df["danger_weight"]
        * df["recency_weight"]
        * (df["severity"] / 5.0)   # normalise severity to 0–1
    )

    # ── Per-district aggregation ───────────────────────────────────────────────
    district_stats = df.groupby("district").agg(
        total_crimes=("id", "count"),
        weighted_score=("composite_weight", "sum"),
        avg_severity=("severity", "mean"),
        max_severity=("severity", "max"),
        unique_crime_types=("crime_type", "nunique"),
        recent_7d=("days_ago", lambda x: (x <= 7).sum()),
        recent_30d=("days_ago", lambda x: (x <= 30).sum()),
    ).reset_index()

    # Normalise weighted_score to 0–100 across all districts
    max_score = district_stats["weighted_score"].max()
    if max_score > 0:
        district_stats["normalised_score"] = (
            district_stats["weighted_score"] / max_score * 100
        )
    else:
        district_stats["normalised_score"] = 0.0

    # Round and clamp
    district_stats["normalised_score"] = district_stats["normalised_score"].clip(0, 100).round(2)

    # ── Build output dict ─────────────────────────────────────────────────────
    results = {}
    for _, row in district_stats.iterrows():
        score = float(row["normalised_score"])
        results[row["district"]] = {
            "score": score,
            "level": _score_to_level(score),
            "components": {
                "total_crimes": int(row["total_crimes"]),
                "recent_7d": int(row["recent_7d"]),
                "recent_30d": int(row["recent_30d"]),
                "avg_severity": round(float(row["avg_severity"]), 2),
                "max_severity": int(row["max_severity"]),
                "unique_crime_types": int(row["unique_crime_types"]),
                "weighted_score_raw": round(float(row["weighted_score"]), 4),
            },
            "computed_at": now.isoformat(),
        }

    # Persist to disk for fast retrieval
    _RISK_SCORES_PATH.write_text(json.dumps(results, indent=2))

    logger.info(
        "risk_scores_computed",
        n_districts=len(results),
        lookback_days=lookback_days,
        top_district=max(results, key=lambda k: results[k]["score"], default=None),
    )

    return results


def get_cached_risk_scores() -> dict[str, dict]:
    """Return last computed risk scores from disk cache."""
    if not _RISK_SCORES_PATH.exists():
        return {}
    try:
        return json.loads(_RISK_SCORES_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def score_single_crime(
    crime_type: str,
    severity: int,
    district: str,
    occurred_at: datetime,
) -> float:
    """
    Compute risk contribution of a single new crime.
    Used to update the district score when a new crime is reported.
    """
    danger = _CRIME_DANGER_WEIGHTS.get(crime_type, _DEFAULT_DANGER_WEIGHT)
    days_ago = (datetime.now(timezone.utc) - occurred_at).total_seconds() / 86400
    recency = 3.0 if days_ago <= 7 else (2.0 if days_ago <= 30 else 1.0)
    severity_norm = severity / 5.0
    raw = danger * recency * severity_norm

    # Retrieve current district score and blend
    cached = get_cached_risk_scores()
    current = cached.get(district, {}).get("score", 0.0)

    # Blend: 80% existing + 20% new crime contribution (capped at 100)
    blended = min(100.0, current * 0.8 + raw * 0.2 * 10)
    return round(blended, 2)


def _score_to_level(score: float) -> str:
    if score < 20:
        return "low"
    elif score < 45:
        return "medium"
    elif score < 70:
        return "high"
    return "critical"
