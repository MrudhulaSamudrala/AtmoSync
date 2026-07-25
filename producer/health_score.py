"""
Container health score calculation for the IoT simulator.

Derives a 0–100 score from current sensor readings against commodity-specific
ideal ranges and operational thresholds for vibration and battery.
"""

from __future__ import annotations

from commodity_config import Commodity

# Normal transit vibration ceiling (g); impacts above this reduce the score.
NORMAL_VIBRATION_MAX = 0.5
# Vibration level at which the vibration component reaches zero.
CRITICAL_VIBRATION = 3.0

# Battery level (%) below which the sensor is considered critically low.
CRITICAL_BATTERY_LEVEL = 20.0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _range_component_score(value: float, ideal_min: float, ideal_max: float) -> float:
    """
    Score how well a reading sits within an ideal min/max range.

    100 inside the range; linear decay outside, reaching 0 when deviation
    equals twice the width of the ideal range.
    """
    if ideal_min <= value <= ideal_max:
        return 100.0

    range_width = max(ideal_max - ideal_min, 0.1)
    deviation = ideal_min - value if value < ideal_min else value - ideal_max
    penalty_ratio = min(deviation / (range_width * 2), 1.0)
    return 100.0 * (1.0 - penalty_ratio)


def _vibration_component_score(vibration: float) -> float:
    """
    Score vibration severity.

    100 at or below normal transit levels; linear decay to 0 at critical levels.
    """
    if vibration <= NORMAL_VIBRATION_MAX:
        return 100.0
    if vibration >= CRITICAL_VIBRATION:
        return 0.0

    ratio = (vibration - NORMAL_VIBRATION_MAX) / (CRITICAL_VIBRATION - NORMAL_VIBRATION_MAX)
    return 100.0 * (1.0 - ratio)


def _battery_component_score(battery_level: float) -> float:
    """
    Score remaining battery charge.

    100 above the critical threshold; linear decay to 0 as battery reaches empty.
    """
    if battery_level >= CRITICAL_BATTERY_LEVEL:
        return 100.0

    return 100.0 * (battery_level / CRITICAL_BATTERY_LEVEL)


def calculate_health_score(
    commodity: Commodity,
    temperature: float,
    humidity: float,
    vibration: float,
    battery_level: float,
) -> float:
    """
    Calculate an overall container health score from 0 to 100.

    The score is the equal-weighted average of four component scores:
    temperature compliance, humidity compliance, vibration severity, and battery level.
    Each component is 100 when conditions are ideal and decreases as readings worsen.
    """
    temp_score = _range_component_score(
        temperature,
        commodity.ideal_temperature_min,
        commodity.ideal_temperature_max,
    )
    humidity_score = _range_component_score(
        humidity,
        commodity.ideal_humidity_min,
        commodity.ideal_humidity_max,
    )
    vibration_score = _vibration_component_score(vibration)
    battery_score = _battery_component_score(battery_level)

    overall = (temp_score + humidity_score + vibration_score + battery_score) / 4.0
    return round(_clamp(overall, 0.0, 100.0), 1)
