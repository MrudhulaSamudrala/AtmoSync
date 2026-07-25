"""
Commodity master data loading and assignment for the IoT simulator.

Configuration is stored separately in datasets/commodities.csv and loaded at startup.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import random

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COMMODITIES_PATH = PROJECT_ROOT / "datasets" / "commodities.csv"

REQUIRED_COLUMNS = (
    "commodity_id",
    "commodity_name",
    "ideal_temperature_min",
    "ideal_temperature_max",
    "ideal_humidity_min",
    "ideal_humidity_max",
    "shelf_life_days",
)


@dataclass(frozen=True)
class Commodity:
    """Storage profile for a single agricultural commodity."""

    commodity_id: str
    commodity_name: str
    ideal_temperature_min: float
    ideal_temperature_max: float
    ideal_humidity_min: float
    ideal_humidity_max: float
    shelf_life_days: int

    @property
    def ideal_temperature(self) -> float:
        """Midpoint of the ideal temperature range (simulation setpoint)."""
        return (self.ideal_temperature_min + self.ideal_temperature_max) / 2

    @property
    def ideal_humidity(self) -> float:
        """Midpoint of the ideal humidity range (simulation setpoint)."""
        return (self.ideal_humidity_min + self.ideal_humidity_max) / 2


def load_commodities(path: Path = DEFAULT_COMMODITIES_PATH) -> list[Commodity]:
    """
    Load commodity master data from a CSV file.

    Returns a list of Commodity records, one per row (excluding the header).
    """
    if not path.is_file():
        raise FileNotFoundError(f"Commodity dataset not found: {path}")

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"Commodity dataset is empty: {path}")

        missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing:
            raise ValueError(f"Commodity dataset missing columns {missing}: {path}")

        commodities: list[Commodity] = []
        for row in reader:
            commodities.append(
                Commodity(
                    commodity_id=row["commodity_id"].strip(),
                    commodity_name=row["commodity_name"].strip(),
                    ideal_temperature_min=float(row["ideal_temperature_min"]),
                    ideal_temperature_max=float(row["ideal_temperature_max"]),
                    ideal_humidity_min=float(row["ideal_humidity_min"]),
                    ideal_humidity_max=float(row["ideal_humidity_max"]),
                    shelf_life_days=int(row["shelf_life_days"]),
                )
            )

    if not commodities:
        raise ValueError(f"Commodity dataset contains no rows: {path}")

    return commodities


def assign_commodity(commodities: list[Commodity]) -> Commodity:
    """Randomly select one commodity from the master list for a new container."""
    return random.choice(commodities)


def get_simulation_profile(commodity: Commodity) -> dict[str, float]:
    """
    Derive temperature/humidity simulation targets from a commodity's ideal ranges.

    Sigma values scale with the configured range so fluctuations stay realistic
    within each commodity's storage window.
    """
    temp_range = commodity.ideal_temperature_max - commodity.ideal_temperature_min
    humidity_range = commodity.ideal_humidity_max - commodity.ideal_humidity_min

    return {
        "temp": commodity.ideal_temperature,
        "temp_sigma": max(0.3, temp_range * 0.1),
        "humidity": commodity.ideal_humidity,
        "humidity_sigma": max(1.0, humidity_range * 0.15),
    }
