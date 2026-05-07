"""
What-If Simulation Engine
--------------------------
Monte Carlo simulation for crime scenario planning.
Models how different interventions affect expected crime rates.

Supported scenarios:
  patrol_increase        — Add N% more patrol officers to a district
  resource_reallocation  — Move resources from low-risk to high-risk areas
  curfew                 — Restrict movement during high-crime hours
  tech_deployment        — Add CCTV / facial recognition coverage
  community_policing     — Sustained community engagement program

Each scenario modifies a probability distribution over crime types
and runs N Monte Carlo trials to estimate the outcome distribution.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

# Crime reduction coefficients per scenario type (empirically tuned)
# Values represent the maximum possible reduction fraction (0–1) at 100% intervention
_SCENARIO_COEFFICIENTS: dict[str, dict[str, float]] = {
    "patrol_increase": {
        "theft":            0.25,
        "robbery":          0.30,
        "assault":          0.20,
        "vandalism":        0.35,
        "drug_offense":     0.15,
        "trespass":         0.40,
        "other":            0.20,
    },
    "resource_reallocation": {
        "theft":            0.15,
        "robbery":          0.20,
        "assault":          0.12,
        "murder":           0.10,
        "fraud":            0.05,
        "drug_offense":     0.12,
        "other":            0.10,
    },
    "curfew": {
        "theft":            0.40,
        "robbery":          0.45,
        "assault":          0.35,
        "vandalism":        0.50,
        "drug_offense":     0.30,
        "sexual_offense":   0.25,
        "trespass":         0.55,
        "other":            0.30,
    },
    "tech_deployment": {
        "theft":            0.30,
        "robbery":          0.35,
        "vandalism":        0.45,
        "trespass":         0.50,
        "drug_offense":     0.20,
        "fraud":            0.25,
        "other":            0.25,
    },
    "community_policing": {
        "assault":          0.20,
        "domestic_violence":0.30,
        "vandalism":        0.25,
        "drug_offense":     0.25,
        "extortion":        0.15,
        "cybercrime":       0.10,
        "other":            0.15,
    },
}

_DEFAULT_COEFFICIENT = 0.10   # For crime types not in the scenario dict


@dataclass
class SimulationResult:
    simulation_id: str
    scenario: str
    district: str
    parameters: dict
    num_simulations: int

    # Before intervention
    baseline_crimes_per_day: float
    baseline_by_type: dict[str, float]

    # After intervention (expected values)
    expected_crimes_per_day: float
    expected_by_type: dict[str, float]

    # Distribution metrics (from Monte Carlo)
    reduction_mean: float
    reduction_std: float
    reduction_p5: float             # 5th percentile (pessimistic)
    reduction_p50: float            # Median
    reduction_p95: float            # 95th percentile (optimistic)
    confidence_interval_95: tuple[float, float]

    # Risk level change
    baseline_risk_level: str
    projected_risk_level: str

    simulated_at: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario": self.scenario,
            "district": self.district,
            "parameters": self.parameters,
            "num_simulations": self.num_simulations,
            "baseline": {
                "crimes_per_day": round(self.baseline_crimes_per_day, 2),
                "by_type": {k: round(v, 3) for k, v in self.baseline_by_type.items()},
                "risk_level": self.baseline_risk_level,
            },
            "projected": {
                "crimes_per_day": round(self.expected_crimes_per_day, 2),
                "by_type": {k: round(v, 3) for k, v in self.expected_by_type.items()},
                "risk_level": self.projected_risk_level,
            },
            "reduction": {
                "mean_pct": round(self.reduction_mean * 100, 2),
                "std_pct": round(self.reduction_std * 100, 2),
                "p5_pct": round(self.reduction_p5 * 100, 2),
                "p50_pct": round(self.reduction_p50 * 100, 2),
                "p95_pct": round(self.reduction_p95 * 100, 2),
                "confidence_interval_95": [
                    round(self.confidence_interval_95[0] * 100, 2),
                    round(self.confidence_interval_95[1] * 100, 2),
                ],
            },
            "simulated_at": self.simulated_at,
            "metadata": self.metadata,
        }


def run_simulation(
    scenario: str,
    district: str,
    parameters: dict[str, Any],
    crime_history: list[dict],
    num_simulations: int = 200,
    lookback_days: int = 30,
) -> SimulationResult:
    """
    Run Monte Carlo simulation for a crime intervention scenario.

    Parameters
    ----------
    scenario         : one of the supported scenario keys
    district         : district to simulate
    parameters       : scenario-specific parameters:
                       patrol_increase:        {"increase_pct": 30}
                       resource_reallocation:  {"from_districts": [...], "to_district": "..."}
                       curfew:                 {"hours": [22, 23, 0, 1, 2, 3], "duration_days": 7}
                       tech_deployment:        {"coverage_pct": 60}
                       community_policing:     {"program_months": 3}
    crime_history    : recent crimes in the district (from DB)
    num_simulations  : Monte Carlo trials
    lookback_days    : window for baseline estimation

    Returns SimulationResult with full distribution statistics.
    """
    if scenario not in _SCENARIO_COEFFICIENTS:
        valid = list(_SCENARIO_COEFFICIENTS.keys())
        raise ValueError(f"Unknown scenario '{scenario}'. Valid: {valid}")

    rng = np.random.default_rng(seed=42)

    # ── Build baseline ─────────────────────────────────────────────────────────
    district_crimes = [c for c in crime_history if c.get("district") == district]
    if not district_crimes:
        district_crimes = crime_history   # fallback: use all

    baseline_per_day = len(district_crimes) / max(lookback_days, 1)
    type_counts: dict[str, int] = {}
    for c in district_crimes:
        ct = c.get("crime_type", "other")
        type_counts[ct] = type_counts.get(ct, 0) + 1

    baseline_by_type = {
        ct: count / max(lookback_days, 1)
        for ct, count in type_counts.items()
    }

    # ── Compute intervention strength ─────────────────────────────────────────
    intervention_strength = _compute_intervention_strength(scenario, parameters)

    # ── Monte Carlo trials ────────────────────────────────────────────────────
    # Each trial adds noise to the intervention strength
    reductions = []
    daily_after_trials = []

    for _ in range(num_simulations):
        # Sample intervention effectiveness with noise (±20%)
        noise = rng.normal(0, 0.2)
        effective_strength = np.clip(intervention_strength + noise, 0.0, 1.0)

        trial_total = 0.0
        for crime_type, base_rate in baseline_by_type.items():
            coeff = _SCENARIO_COEFFICIENTS[scenario].get(crime_type, _DEFAULT_COEFFICIENT)
            # Reduction fraction for this crime type in this trial
            reduction_frac = coeff * effective_strength
            # Add Poisson noise to the crime rate
            reduced_rate = max(0.0, base_rate * (1 - reduction_frac))
            sampled_rate = rng.poisson(max(0.01, reduced_rate))
            trial_total += sampled_rate

        daily_after_trials.append(trial_total)
        if baseline_per_day > 0:
            reductions.append((baseline_per_day - trial_total) / baseline_per_day)
        else:
            reductions.append(0.0)

    # ── Compute statistics ────────────────────────────────────────────────────
    reductions_arr = np.array(reductions)
    daily_after_arr = np.array(daily_after_trials)

    expected_per_day = float(np.mean(daily_after_arr))
    reduction_mean = float(np.mean(reductions_arr))
    reduction_std = float(np.std(reductions_arr))
    reduction_p5 = float(np.percentile(reductions_arr, 5))
    reduction_p50 = float(np.percentile(reductions_arr, 50))
    reduction_p95 = float(np.percentile(reductions_arr, 95))

    # 95% CI on daily crime count
    ci_low = float(np.percentile(daily_after_arr, 2.5))
    ci_high = float(np.percentile(daily_after_arr, 97.5))

    # Project by-type expected rates
    expected_by_type = {}
    for crime_type, base_rate in baseline_by_type.items():
        coeff = _SCENARIO_COEFFICIENTS[scenario].get(crime_type, _DEFAULT_COEFFICIENT)
        expected_by_type[crime_type] = max(
            0.0, base_rate * (1 - coeff * intervention_strength)
        )

    # Risk levels
    baseline_risk = _daily_rate_to_risk_level(baseline_per_day)
    projected_risk = _daily_rate_to_risk_level(expected_per_day)

    logger.info(
        "simulation_complete",
        scenario=scenario,
        district=district,
        n_trials=num_simulations,
        baseline=round(baseline_per_day, 2),
        expected=round(expected_per_day, 2),
        reduction_mean_pct=round(reduction_mean * 100, 1),
    )

    return SimulationResult(
        simulation_id=str(uuid.uuid4()),
        scenario=scenario,
        district=district,
        parameters=parameters,
        num_simulations=num_simulations,
        baseline_crimes_per_day=baseline_per_day,
        baseline_by_type=baseline_by_type,
        expected_crimes_per_day=expected_per_day,
        expected_by_type=expected_by_type,
        reduction_mean=reduction_mean,
        reduction_std=reduction_std,
        reduction_p5=reduction_p5,
        reduction_p50=reduction_p50,
        reduction_p95=reduction_p95,
        confidence_interval_95=(ci_low, ci_high),
        baseline_risk_level=baseline_risk,
        projected_risk_level=projected_risk,
        simulated_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "intervention_strength": round(float(intervention_strength), 4),
            "lookback_days": lookback_days,
            "n_crimes_in_baseline": len(district_crimes),
        },
    )


def _compute_intervention_strength(
    scenario: str, parameters: dict[str, Any]
) -> float:
    """Convert scenario parameters to a 0–1 intervention strength."""
    if scenario == "patrol_increase":
        pct = float(parameters.get("increase_pct", 20))
        return min(pct / 100.0, 1.0)

    elif scenario == "resource_reallocation":
        # Effectiveness depends on how well resources are matched to risk
        match_quality = float(parameters.get("match_quality", 0.7))
        return match_quality * 0.6   # Max 60% strength

    elif scenario == "curfew":
        hours = parameters.get("hours", [22, 23, 0, 1, 2, 3])
        duration_days = float(parameters.get("duration_days", 7))
        hour_fraction = len(hours) / 24.0
        duration_factor = min(duration_days / 30.0, 1.0)
        return hour_fraction * duration_factor

    elif scenario == "tech_deployment":
        coverage_pct = float(parameters.get("coverage_pct", 50))
        return min(coverage_pct / 100.0, 1.0) * 0.8   # Max 80% effective

    elif scenario == "community_policing":
        months = float(parameters.get("program_months", 3))
        # Longer programs are more effective, with diminishing returns
        return min(1 - math.exp(-months / 6), 0.7)

    return 0.3   # Default moderate intervention


def _daily_rate_to_risk_level(daily_rate: float) -> str:
    if daily_rate < 1:
        return "low"
    elif daily_rate < 3:
        return "medium"
    elif daily_rate < 7:
        return "high"
    return "critical"


def list_scenarios() -> list[dict[str, Any]]:
    """Return metadata about all available simulation scenarios."""
    return [
        {
            "id": "patrol_increase",
            "name": "Patrol Increase",
            "description": "Increase number of patrol officers in the district",
            "parameters": {"increase_pct": {"type": "int", "range": [5, 100], "default": 30}},
        },
        {
            "id": "resource_reallocation",
            "name": "Resource Reallocation",
            "description": "Move resources from low-risk to high-risk areas",
            "parameters": {"match_quality": {"type": "float", "range": [0.1, 1.0], "default": 0.7}},
        },
        {
            "id": "curfew",
            "name": "Night Curfew",
            "description": "Restrict movement during specified hours",
            "parameters": {
                "hours": {"type": "list[int]", "default": [22, 23, 0, 1, 2, 3]},
                "duration_days": {"type": "int", "range": [1, 30], "default": 7},
            },
        },
        {
            "id": "tech_deployment",
            "name": "Technology Deployment",
            "description": "Deploy CCTV and smart surveillance systems",
            "parameters": {"coverage_pct": {"type": "int", "range": [10, 100], "default": 60}},
        },
        {
            "id": "community_policing",
            "name": "Community Policing",
            "description": "Long-term community engagement program",
            "parameters": {"program_months": {"type": "int", "range": [1, 12], "default": 3}},
        },
    ]
