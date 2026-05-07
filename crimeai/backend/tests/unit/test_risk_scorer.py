"""Unit tests for risk scoring module."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from app.ml.prediction.risk_scorer import (
    compute_district_risk_scores,
    score_single_crime,
    _score_to_level,
    _CRIME_DANGER_WEIGHTS,
)


def _make_records(
    district: str,
    crime_type: str = "theft",
    n: int = 10,
    days_ago: int = 5,
    severity: int = 3,
) -> list[dict]:
    base_time = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return [
        {
            "id": f"crime-{i}",
            "district": district,
            "crime_type": crime_type,
            "severity": severity,
            "occurred_at": (base_time + timedelta(hours=i)).isoformat(),
        }
        for i in range(n)
    ]


class TestScoreToLevel:
    def test_low(self):
        assert _score_to_level(10.0) == "low"

    def test_medium(self):
        assert _score_to_level(30.0) == "medium"

    def test_high(self):
        assert _score_to_level(60.0) == "high"

    def test_critical(self):
        assert _score_to_level(85.0) == "critical"


class TestComputeDistrictRiskScores:
    def test_empty_records_returns_empty(self):
        result = compute_district_risk_scores([])
        assert result == {}

    def test_single_district_gets_score(self):
        records = _make_records("Connaught Place", n=15)
        result = compute_district_risk_scores(records)
        assert "Connaught Place" in result
        data = result["Connaught Place"]
        assert "score" in data
        assert "level" in data
        assert "components" in data
        assert 0 <= data["score"] <= 100

    def test_more_crimes_higher_score(self):
        """District with more recent crimes should score higher."""
        low_records = _make_records("Safe District", n=2, days_ago=60)
        high_records = _make_records("Hotspot District", n=30, days_ago=3)
        result = compute_district_risk_scores(low_records + high_records)

        assert "Safe District" in result
        assert "Hotspot District" in result
        # The hotspot should score higher
        assert result["Hotspot District"]["score"] >= result["Safe District"]["score"]

    def test_murder_scores_higher_than_vandalism(self):
        """High-danger crimes should produce higher scores than low-danger crimes."""
        murder_records = _make_records("DistrictA", crime_type="murder", n=5, severity=5)
        vandalism_records = _make_records("DistrictB", crime_type="vandalism", n=5, severity=1)
        result = compute_district_risk_scores(murder_records + vandalism_records)
        assert result["DistrictA"]["score"] > result["DistrictB"]["score"]

    def test_recent_crimes_score_higher_than_old(self):
        """Recent crimes (3d ago) should score higher than old crimes (60d ago)."""
        recent = _make_records("RecentDistrict", n=10, days_ago=3)
        old = _make_records("OldDistrict", n=10, days_ago=80)
        result = compute_district_risk_scores(recent + old)
        assert result["RecentDistrict"]["score"] >= result["OldDistrict"]["score"]

    def test_components_structure(self):
        records = _make_records("TestDistrict", n=10)
        result = compute_district_risk_scores(records)
        components = result["TestDistrict"]["components"]
        for key in ["total_crimes", "recent_7d", "recent_30d", "avg_severity"]:
            assert key in components

    def test_max_score_is_100(self):
        """Normalised scores must not exceed 100."""
        records = _make_records("MaxDistrict", crime_type="murder", n=100, days_ago=1, severity=5)
        result = compute_district_risk_scores(records)
        for dist_data in result.values():
            assert dist_data["score"] <= 100.0

    def test_all_danger_weights_defined(self):
        """All crime types listed in system should have a danger weight."""
        from app.schemas.crime import VALID_CRIME_TYPES
        # Check major types have explicit weights
        for ct in ["theft", "assault", "robbery", "murder", "fraud"]:
            assert ct in _CRIME_DANGER_WEIGHTS, f"Missing danger weight for: {ct}"


class TestScoreSingleCrime:
    def test_returns_float_in_range(self):
        score = score_single_crime(
            crime_type="theft",
            severity=2,
            district="TestArea",
            occurred_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_murder_higher_than_vandalism(self):
        now = datetime.now(timezone.utc) - timedelta(days=1)
        murder_score = score_single_crime("murder", 5, "Area1", now)
        vandalism_score = score_single_crime("vandalism", 1, "Area1", now)
        assert murder_score > vandalism_score
