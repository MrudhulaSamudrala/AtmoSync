"""
Spoilage estimation for the IoT simulator.

Models cumulative spoilage from commodity storage profiles, live sensor readings,
and the composite health score. Spoilage accumulates over time and accelerates
when containers operate outside ideal conditions.
"""

from __future__ import annotations

from commodity_config import Commodity

SECONDS_PER_DAY = 86_400.0

RISK_LOW = "Low"
RISK_MEDIUM = "Medium"
RISK_HIGH = "High"
RISK_CRITICAL = "Critical"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _single_axis_stress(value: float, ideal_min: float, ideal_max: float) -> float:
    """
    Normalised stress for one sensor axis.

    Returns 0 inside the ideal range; scales with distance outside the range,
    capped at 2.0 (twice the ideal window width).
    """
    if ideal_min <= value <= ideal_max:
        return 0.0

    range_width = max(ideal_max - ideal_min, 0.1)
    deviation = ideal_min - value if value < ideal_min else value - ideal_max
    return min(deviation / range_width, 2.0)


def calculate_environmental_stress(
    commodity: Commodity,
    temperature: float,
    humidity: float,
) -> float:
    """
    Combined temperature and humidity stress relative to commodity ideal ranges.

    Average of per-axis stress; 0 when both readings are in range.
    """
    temp_stress = _single_axis_stress(
        temperature,
        commodity.ideal_temperature_min,
        commodity.ideal_temperature_max,
    )
    humidity_stress = _single_axis_stress(
        humidity,
        commodity.ideal_humidity_min,
        commodity.ideal_humidity_max,
    )
    return (temp_stress + humidity_stress) / 2.0


def calculate_health_acceleration_factor(health_score: float) -> float:
    """
    Multiplier applied to spoilage rate based on container health.

    1.0 at perfect health (100); 2.0 at zero health — poor conditions double
    the effective spoilage rate.
    """
    return 1.0 + (100.0 - _clamp(health_score, 0.0, 100.0)) / 100.0


def calculate_spoilage_increment(
    commodity: Commodity,
    environmental_stress: float,
    health_score: float,
    interval_seconds: float,
) -> float:
    """
    Percentage points to add to cumulative spoilage for one simulation tick.

    Baseline rate consumes the full shelf life under ideal conditions; stress
    and poor health accelerate the rate multiplicatively.
    """
    day_fraction = interval_seconds / SECONDS_PER_DAY
    baseline_daily_rate = 100.0 / commodity.shelf_life_days
    stress_factor = 1.0 + environmental_stress
    health_factor = calculate_health_acceleration_factor(health_score)
    return baseline_daily_rate * day_fraction * stress_factor * health_factor


def advance_spoilage_percentage(current_spoilage: float, increment: float) -> float:
    """Apply a spoilage increment and clamp the result to 0–100%."""
    return round(_clamp(current_spoilage + increment, 0.0, 100.0), 2)


def calculate_remaining_shelf_life_days(
    commodity: Commodity,
    spoilage_percentage: float,
) -> float:
    """
    Estimate remaining shelf life from cumulative spoilage progress.

    Linearly maps spoilage percentage onto the commodity's configured shelf life.
    """
    remaining = commodity.shelf_life_days * (1.0 - spoilage_percentage / 100.0)
    return round(_clamp(remaining, 0.0, float(commodity.shelf_life_days)), 2)


def classify_spoilage_risk(spoilage_percentage: float) -> str:
    """Map spoilage percentage to a discrete risk level."""
    if spoilage_percentage <= 20.0:
        return RISK_LOW
    if spoilage_percentage <= 50.0:
        return RISK_MEDIUM
    if spoilage_percentage <= 80.0:
        return RISK_HIGH
    return RISK_CRITICAL


def estimate_spoilage_metrics(
    commodity: Commodity,
    temperature: float,
    humidity: float,
    health_score: float,
    current_spoilage_percentage: float,
    interval_seconds: float,
) -> dict[str, float | str]:
    """
    Advance spoilage state and return all spoilage fields for a telemetry event.

    Returns spoilage_percentage, remaining_shelf_life_days, and spoilage_risk_level.
    """
    stress = calculate_environmental_stress(commodity, temperature, humidity)
    increment = calculate_spoilage_increment(
        commodity,
        stress,
        health_score,
        interval_seconds,
    )
    spoilage_percentage = advance_spoilage_percentage(current_spoilage_percentage, increment)
    remaining_shelf_life_days = calculate_remaining_shelf_life_days(commodity, spoilage_percentage)
    spoilage_risk_level = classify_spoilage_risk(spoilage_percentage)

    return {
        "spoilage_percentage": spoilage_percentage,
        "remaining_shelf_life_days": remaining_shelf_life_days,
        "spoilage_risk_level": spoilage_risk_level,
    }
