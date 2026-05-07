"""Unit tests for hotspot predictor module."""
from __future__ import annotations

import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.ml.prediction.hotspot_predictor import (
    _build_features,
    _hour_to_time_bucket,
    _prob_to_risk_level,
    get_model_metadata,
    train_hotspot_model,
)
import pandas as pd


def _make_training_records(n: int = 100) -> list[dict]:
    """Generate synthetic training records."""
    import random
    random.seed(42)
    districts = ["Connaught Place", "Rohini", "Dwarka", "Saket", "Karol Bagh"]
    crime_types = ["theft", "assault", "robbery", "fraud", "vandalism"]
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    records = []
    for i in range(n):
        from datetime import timedelta
        records.append({
            "id": f"crime-{i}",
            "district": random.choice(districts),
            "crime_type": random.choice(crime_types),
            "severity": random.randint(1, 5),
            "occurred_at": (base + timedelta(hours=random.randint(0, 8760))).isoformat(),
        })
    return records


class TestTimeBucket:
    def test_night(self):
        assert _hour_to_time_bucket(23) == 0
        assert _hour_to_time_bucket(3) == 0

    def test_morning(self):
        assert _hour_to_time_bucket(8) == 1

    def test_afternoon(self):
        assert _hour_to_time_bucket(14) == 2

    def test_evening(self):
        assert _hour_to_time_bucket(20) == 3


class TestProbToRiskLevel:
    def test_levels(self):
        assert _prob_to_risk_level(0.1) == "low"
        assert _prob_to_risk_level(0.3) == "medium"
        assert _prob_to_risk_level(0.6) == "high"
        assert _prob_to_risk_level(0.9) == "critical"


class TestBuildFeatures:
    def test_columns_created(self):
        records = _make_training_records(20)
        df = pd.DataFrame(records)
        result = _build_features(df)
        for col in ["hour", "day_of_week", "month", "is_weekend", "is_night", "rolling_7d_avg"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_is_weekend_correct(self):
        """day_of_week 5 = Saturday should be weekend."""
        df = pd.DataFrame([{
            "id": "x",
            "district": "Test",
            "crime_type": "theft",
            "severity": 2,
            "occurred_at": "2024-01-06T10:00:00+00:00",   # Saturday
        }])
        result = _build_features(df)
        assert result["is_weekend"].iloc[0] == 1

    def test_is_night_correct(self):
        df = pd.DataFrame([{
            "id": "x",
            "district": "Test",
            "crime_type": "theft",
            "severity": 2,
            "occurred_at": "2024-01-01T23:00:00+00:00",   # 11pm — night
        }])
        result = _build_features(df)
        assert result["is_night"].iloc[0] == 1


class TestTrainHotspotModel:
    def test_insufficient_data_raises(self):
        from app.core.exceptions import MLServiceError
        records = _make_training_records(10)   # < 50 minimum
        with pytest.raises(MLServiceError, match="Insufficient data"):
            train_hotspot_model(records)

    def test_training_produces_valid_result(self):
        """Training on 100 synthetic records should complete without error."""
        records = _make_training_records(100)
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the model save path to temp dir
            with patch(
                "app.ml.prediction.hotspot_predictor._MODEL_DIR",
                Path(tmpdir),
            ), patch(
                "app.ml.prediction.hotspot_predictor._MODEL_PATH",
                Path(tmpdir) / "hotspot_rf.joblib",
            ), patch(
                "app.ml.prediction.hotspot_predictor._ENCODER_PATH",
                Path(tmpdir) / "district_encoder.joblib",
            ), patch(
                "app.ml.prediction.hotspot_predictor._METADATA_PATH",
                Path(tmpdir) / "hotspot_metadata.json",
            ):
                result = train_hotspot_model(records)

        assert 0.0 <= result.accuracy <= 1.0
        assert result.n_training_samples > 0
        assert "hour" in result.feature_importances
        assert result.trained_at is not None
