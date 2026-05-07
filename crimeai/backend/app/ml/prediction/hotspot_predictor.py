"""
Hotspot Prediction Module
--------------------------
Uses a Random Forest classifier to predict which districts/cells
will be high-crime in the next 24 hours, based on:
  - Historical crime patterns (day of week, hour, month)
  - Rolling crime counts per district
  - Seasonal trends

The model is trained on the full crime history and serialised
with joblib. It is retrained automatically every 7 days via
the Celery beat schedule.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from app.core.exceptions import MLServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Model persistence path
_MODEL_DIR = Path(__file__).parent / "saved"
_MODEL_PATH = _MODEL_DIR / "hotspot_rf.joblib"
_ENCODER_PATH = _MODEL_DIR / "district_encoder.joblib"
_METADATA_PATH = _MODEL_DIR / "hotspot_metadata.json"


def _ensure_model_dir() -> None:
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ── Feature engineering ───────────────────────────────────────────────────────

def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract temporal and spatial features from a crimes DataFrame.

    Input columns: district, crime_type, severity, occurred_at (datetime)
    Output: feature matrix ready for sklearn
    """
    df = df.copy()
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True)

    # Temporal features
    df["hour"] = df["occurred_at"].dt.hour
    df["day_of_week"] = df["occurred_at"].dt.dayofweek   # 0=Mon, 6=Sun
    df["month"] = df["occurred_at"].dt.month
    df["day_of_month"] = df["occurred_at"].dt.day
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_night"] = ((df["hour"] >= 22) | (df["hour"] <= 5)).astype(int)
    df["quarter"] = df["occurred_at"].dt.quarter

    # Time-of-day bucket: 0=night(22-5), 1=morning(6-11), 2=afternoon(12-17), 3=evening(18-21)
    df["time_bucket"] = pd.cut(
        df["hour"],
        bins=[-1, 5, 11, 17, 21, 24],
        labels=[0, 1, 2, 3, 0],
    ).astype(int)

    # Rolling crime density per district (last 7 days)
    df = df.sort_values("occurred_at")
    df["date"] = df["occurred_at"].dt.date
    daily_counts = (
        df.groupby(["district", "date"])
        .size()
        .reset_index(name="daily_count")
    )
    daily_counts["date"] = pd.to_datetime(daily_counts["date"])
    # 7-day rolling average per district
    rolling = (
        daily_counts.sort_values("date")
        .groupby("district")["daily_count"]
        .transform(lambda x: x.rolling(7, min_periods=1).mean())
    )
    daily_counts["rolling_7d_avg"] = rolling
    df = df.merge(
        daily_counts[["district", "date", "rolling_7d_avg"]],
        left_on=["district", "date"],
        right_on=["district", "date"],
        how="left",
    )
    df["rolling_7d_avg"] = df["rolling_7d_avg"].fillna(0)

    # Severity encoding
    df["severity_norm"] = df["severity"] / 5.0

    return df


def _make_feature_matrix(df: pd.DataFrame, district_encoder: LabelEncoder) -> np.ndarray:
    """Convert engineered DataFrame to numpy feature matrix."""
    # Encode district
    try:
        district_encoded = district_encoder.transform(df["district"].fillna("Unknown"))
    except ValueError:
        # Unseen districts → use last known class
        district_encoded = np.zeros(len(df), dtype=int)

    features = np.column_stack([
        district_encoded,
        df["hour"].values,
        df["day_of_week"].values,
        df["month"].values,
        df["day_of_month"].values,
        df["is_weekend"].values,
        df["is_night"].values,
        df["quarter"].values,
        df["time_bucket"].values,
        df.get("rolling_7d_avg", pd.Series(np.zeros(len(df)))).values,
        df.get("severity_norm", pd.Series(np.ones(len(df)) * 0.4)).values,
    ])
    return features


# ── Training ──────────────────────────────────────────────────────────────────

@dataclass
class TrainingResult:
    accuracy: float
    auc_roc: float
    n_training_samples: int
    n_features: int
    feature_importances: dict[str, float]
    trained_at: str


def train_hotspot_model(crime_records: list[dict]) -> TrainingResult:
    """
    Train a Random Forest model to predict if a district will be a hotspot.

    A district-hour combination is labelled as 'hotspot' (1) if it has
    >= 2 crimes in that hour, else 0.

    crime_records: list of dicts with keys: district, crime_type, severity, occurred_at
    """
    _ensure_model_dir()

    if len(crime_records) < 50:
        raise MLServiceError(
            "Insufficient data for training",
            detail={"n_records": len(crime_records), "minimum": 50},
        )

    df = pd.DataFrame(crime_records)
    df = _build_features(df)

    # Create target: is this district/hour combination a 'hotspot'?
    df["occurred_at_dt"] = pd.to_datetime(df["occurred_at"], utc=True)
    df["hour_slot"] = df["occurred_at_dt"].dt.floor("H")
    hourly_counts = df.groupby(["district", "hour_slot"]).size().reset_index(name="crime_count")
    df = df.merge(
        hourly_counts,
        left_on=["district", "hour_slot"],
        right_on=["district", "hour_slot"],
        how="left",
    )
    # Hotspot threshold: >= 2 crimes in the same district+hour
    df["is_hotspot"] = (df["crime_count"] >= 2).astype(int)

    # Encode districts
    district_encoder = LabelEncoder()
    df["district"] = df["district"].fillna("Unknown")
    district_encoder.fit(df["district"])

    X = _make_feature_matrix(df, district_encoder)
    y = df["is_hotspot"].values

    # Class imbalance: hotspots are rare — use class_weight balanced
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if y.sum() > 5 else None
    )

    model = RandomForestClassifier(
        n_estimators=150,
        max_depth=12,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    accuracy = float(model.score(X_test, y_test))
    try:
        auc = float(roc_auc_score(y_test, y_prob))
    except ValueError:
        auc = 0.0

    # Feature names (must match _make_feature_matrix column order)
    feature_names = [
        "district", "hour", "day_of_week", "month", "day_of_month",
        "is_weekend", "is_night", "quarter", "time_bucket",
        "rolling_7d_avg", "severity_norm",
    ]
    importances = dict(zip(feature_names, model.feature_importances_.tolist()))

    # Persist
    joblib.dump(model, _MODEL_PATH)
    joblib.dump(district_encoder, _ENCODER_PATH)
    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_training_samples": len(X_train),
        "n_features": X.shape[1],
        "accuracy": accuracy,
        "auc_roc": auc,
        "feature_importances": importances,
        "districts": district_encoder.classes_.tolist(),
    }
    _METADATA_PATH.write_text(json.dumps(metadata, indent=2))

    logger.info(
        "hotspot_model_trained",
        accuracy=round(accuracy, 4),
        auc_roc=round(auc, 4),
        n_samples=len(X_train),
    )

    return TrainingResult(
        accuracy=accuracy,
        auc_roc=auc,
        n_training_samples=len(X_train),
        n_features=X.shape[1],
        feature_importances=importances,
        trained_at=metadata["trained_at"],
    )


# ── Inference ─────────────────────────────────────────────────────────────────

def _load_model() -> tuple:
    """Load model and encoder from disk. Raises MLServiceError if not found."""
    if not _MODEL_PATH.exists():
        raise MLServiceError(
            "Hotspot model not trained yet",
            detail={"hint": "POST /api/v1/ml/hotspot-prediction to trigger training"},
        )
    model = joblib.load(_MODEL_PATH)
    encoder = joblib.load(_ENCODER_PATH)
    return model, encoder


def predict_hotspots(
    districts: list[str],
    target_datetime: datetime | None = None,
) -> list[dict]:
    """
    Predict hotspot probability for a list of districts at a given datetime.

    Returns list of {district, hotspot_probability, is_hotspot, risk_level}
    sorted by probability descending.
    """
    model, encoder = _load_model()

    if target_datetime is None:
        target_datetime = datetime.now(timezone.utc)

    results = []
    for district in districts:
        # Build a single-row feature vector for this district + time
        row = pd.DataFrame([{
            "district": district,
            "hour": target_datetime.hour,
            "day_of_week": target_datetime.weekday(),
            "month": target_datetime.month,
            "day_of_month": target_datetime.day,
            "is_weekend": int(target_datetime.weekday() >= 5),
            "is_night": int(target_datetime.hour >= 22 or target_datetime.hour <= 5),
            "quarter": (target_datetime.month - 1) // 3 + 1,
            "time_bucket": _hour_to_time_bucket(target_datetime.hour),
            "rolling_7d_avg": 0.0,   # Will be populated from DB in production
            "severity_norm": 0.5,
        }])

        X = _make_feature_matrix(row, encoder)
        prob = float(model.predict_proba(X)[0, 1])

        results.append({
            "district": district,
            "hotspot_probability": round(prob, 4),
            "is_hotspot": prob >= 0.5,
            "risk_level": _prob_to_risk_level(prob),
            "predicted_for": target_datetime.isoformat(),
        })

    return sorted(results, key=lambda x: x["hotspot_probability"], reverse=True)


def predict_next_24h(districts: list[str]) -> list[dict]:
    """
    Predict hourly hotspot risk for each district over the next 24 hours.
    Returns timeline data suitable for the dashboard chart.
    """
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    results = []
    for hour_offset in range(24):
        target_dt = now + timedelta(hours=hour_offset)
        hour_predictions = predict_hotspots(districts, target_dt)
        results.append({
            "datetime": target_dt.isoformat(),
            "hour": target_dt.hour,
            "predictions": hour_predictions,
        })
    return results


def _hour_to_time_bucket(hour: int) -> int:
    if hour <= 5 or hour >= 22:
        return 0   # night
    elif hour <= 11:
        return 1   # morning
    elif hour <= 17:
        return 2   # afternoon
    else:
        return 3   # evening


def _prob_to_risk_level(prob: float) -> str:
    if prob < 0.25:
        return "low"
    elif prob < 0.5:
        return "medium"
    elif prob < 0.75:
        return "high"
    return "critical"


def get_model_metadata() -> dict:
    """Return training metadata if model exists."""
    if not _METADATA_PATH.exists():
        return {"status": "not_trained"}
    return json.loads(_METADATA_PATH.read_text())
