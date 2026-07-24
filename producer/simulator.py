"""
AtmoSync IoT sensor simulator for agricultural shipping containers.

Generates continuous JSON sensor events conforming to config/sensor_schema.json.
"""

from __future__ import annotations

import json
import math
import random
import string
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import os

# ---------------------------------------------------------------------------
# Paths & configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "config" / "sensor_schema.json"

# ISO 6346 owner codes commonly used on refrigerated containers.
CONTAINER_PREFIXES = ("MSCU", "HLXU", "TCLU", "CMAU", "MAEU")

# Approximate starting coordinates for major agricultural export corridors.
ROUTE_ORIGINS = (
    (19.4326, -99.1332),   # Mexico City region
    (-23.5505, -46.6333),  # São Paulo region
    (13.7563, 100.5018),   # Bangkok region
    (-33.8688, 151.2093),  # Sydney region
    (36.7783, -119.4179),  # California Central Valley
    (4.7110, -74.0721),    # Bogotá region
    (-34.6037, -58.3816),  # Buenos Aires region
    (14.5995, 120.9842),   # Manila region
)

# Target cold-chain conditions per commodity (centre points for simulation).
COMMODITY_PROFILES = {
    "avocados": {"temp": 5.0, "temp_sigma": 0.4, "humidity": 90.0, "humidity_sigma": 2.0},
    "blueberries": {"temp": 1.0, "temp_sigma": 0.3, "humidity": 92.0, "humidity_sigma": 1.5},
    "strawberries": {"temp": 0.5, "temp_sigma": 0.3, "humidity": 93.0, "humidity_sigma": 1.5},
    "grapes": {"temp": 1.0, "temp_sigma": 0.3, "humidity": 91.0, "humidity_sigma": 2.0},
    "mangoes": {"temp": 12.0, "temp_sigma": 0.5, "humidity": 88.0, "humidity_sigma": 2.5},
    "citrus": {"temp": 6.0, "temp_sigma": 0.4, "humidity": 89.0, "humidity_sigma": 2.0},
    "leafy_greens": {"temp": 2.0, "temp_sigma": 0.3, "humidity": 96.0, "humidity_sigma": 1.0},
    "tomatoes": {"temp": 11.0, "temp_sigma": 0.4, "humidity": 87.0, "humidity_sigma": 2.0},
    "bananas": {"temp": 14.0, "temp_sigma": 0.5, "humidity": 90.0, "humidity_sigma": 2.0},
    "apples": {"temp": 2.0, "temp_sigma": 0.3, "humidity": 90.0, "humidity_sigma": 2.0},
}


@dataclass
class SchemaConstraints:
    """Numeric and enum bounds extracted from the sensor JSON schema."""

    commodities: list[str]
    transport_statuses: list[str]
    temp_min: float
    temp_max: float
    humidity_min: float
    humidity_max: float
    vibration_min: float
    vibration_max: float
    battery_min: float
    battery_max: float
    lat_min: float
    lat_max: float
    lng_min: float
    lng_max: float


@dataclass
class ContainerState:
    """Mutable runtime state for a single simulated container."""

    container_id: str
    shipment_id: str
    commodity_name: str
    latitude: float
    longitude: float
    temperature: float
    humidity: float
    vibration: float
    battery_level: float
    transport_status: str
    heading: float  # movement bearing in radians
    tick: int = 0


def load_schema(schema_path: Path = DEFAULT_SCHEMA_PATH) -> dict:
    """Load and return the sensor event JSON schema from disk."""
    with schema_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def parse_schema_constraints(schema: dict) -> SchemaConstraints:
    """Extract enum lists and numeric min/max values from the JSON schema."""
    props = schema["properties"]
    return SchemaConstraints(
        commodities=props["commodity_name"]["enum"],
        transport_statuses=props["transport_status"]["enum"],
        temp_min=props["temperature"]["minimum"],
        temp_max=props["temperature"]["maximum"],
        humidity_min=props["humidity"]["minimum"],
        humidity_max=props["humidity"]["maximum"],
        vibration_min=props["vibration"]["minimum"],
        vibration_max=props["vibration"]["maximum"],
        battery_min=props["battery_level"]["minimum"],
        battery_max=props["battery_level"]["maximum"],
        lat_min=props["latitude"]["minimum"],
        lat_max=props["latitude"]["maximum"],
        lng_min=props["longitude"]["minimum"],
        lng_max=props["longitude"]["maximum"],
    )


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Restrict a numeric value to an inclusive min/max range."""
    return max(minimum, min(maximum, value))


def generate_container_id() -> str:
    """Create an ISO 6346-style container ID (4 letters + 7 digits)."""
    prefix = random.choice(CONTAINER_PREFIXES)
    suffix = "".join(random.choices(string.digits, k=7))
    return f"{prefix}{suffix}"


def generate_shipment_id() -> str:
    """Create a shipment ID matching the schema pattern SHP-YYYYMMDD-NNNN."""
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    sequence = random.randint(1, 9999)
    return f"SHP-{date_part}-{sequence:04d}"


def get_commodity_profile(commodity_name: str) -> dict[str, float]:
    """Return simulation targets for a commodity, falling back to a safe default."""
    return COMMODITY_PROFILES.get(
        commodity_name,
        {"temp": 4.0, "temp_sigma": 0.5, "humidity": 90.0, "humidity_sigma": 2.0},
    )


def create_container_state(constraints: SchemaConstraints) -> ContainerState:
    """Initialize a single container with realistic starting telemetry."""
    commodity = random.choice(constraints.commodities)
    profile = get_commodity_profile(commodity)
    origin_lat, origin_lng = random.choice(ROUTE_ORIGINS)

    # Scatter containers near their route origin.
    latitude = origin_lat + random.uniform(-0.5, 0.5)
    longitude = origin_lng + random.uniform(-0.5, 0.5)

    return ContainerState(
        container_id=generate_container_id(),
        shipment_id=generate_shipment_id(),
        commodity_name=commodity,
        latitude=clamp(latitude, constraints.lat_min, constraints.lat_max),
        longitude=clamp(longitude, constraints.lng_min, constraints.lng_max),
        temperature=clamp(
            random.gauss(profile["temp"], profile["temp_sigma"]),
            constraints.temp_min,
            constraints.temp_max,
        ),
        humidity=clamp(
            random.gauss(profile["humidity"], profile["humidity_sigma"]),
            constraints.humidity_min,
            constraints.humidity_max,
        ),
        vibration=clamp(random.uniform(0.05, 0.25), constraints.vibration_min, constraints.vibration_max),
        battery_level=random.uniform(85.0, 100.0),
        transport_status=random.choice(["loading", "in_transit", "in_transit", "in_transit"]),
        heading=random.uniform(0, 2 * math.pi),
    )


def initialize_fleet(count: int, constraints: SchemaConstraints) -> list[ContainerState]:
    """Create the full set of simulated containers."""
    return [create_container_state(constraints) for _ in range(count)]


def update_temperature(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Drift temperature around the commodity target with small random noise."""
    profile = get_commodity_profile(state.commodity_name)
    # Mean-reverting random walk keeps readings near the ideal cold-chain setpoint.
    drift = (profile["temp"] - state.temperature) * 0.05
    noise = random.gauss(0, profile["temp_sigma"] * 0.15)
    state.temperature = clamp(
        state.temperature + drift + noise,
        constraints.temp_min,
        constraints.temp_max,
    )


def update_humidity(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Drift humidity around the commodity target with constrained noise."""
    profile = get_commodity_profile(state.commodity_name)
    drift = (profile["humidity"] - state.humidity) * 0.04
    noise = random.gauss(0, profile["humidity_sigma"] * 0.2)
    state.humidity = clamp(
        state.humidity + drift + noise,
        constraints.humidity_min,
        constraints.humidity_max,
    )


def update_battery(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Slowly drain battery charge on each tick."""
    drain = random.uniform(0.004, 0.012)
    state.battery_level = clamp(
        state.battery_level - drain,
        constraints.battery_min,
        constraints.battery_max,
    )


def update_position(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Nudge latitude/longitude to simulate container movement along a route."""
    # ~0.0001 degrees ≈ 11 m; small per-second step mimics truck/vessel travel.
    speed = random.uniform(0.00005, 0.00015)
    state.latitude += speed * math.cos(state.heading) + random.gauss(0, 0.00001)
    state.longitude += speed * math.sin(state.heading) + random.gauss(0, 0.00001)
    state.latitude = clamp(state.latitude, constraints.lat_min, constraints.lat_max)
    state.longitude = clamp(state.longitude, constraints.lng_min, constraints.lng_max)

    # Occasionally adjust heading for route curvature.
    if random.random() < 0.05:
        state.heading += random.uniform(-0.3, 0.3)


def update_vibration(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Simulate normal transit vibration with occasional road/port impacts."""
    if random.random() < 0.02:
        spike = random.uniform(0.8, 2.5)
    else:
        spike = 0.0
    base = random.uniform(0.05, 0.35)
    state.vibration = clamp(base + spike, constraints.vibration_min, constraints.vibration_max)


def update_transport_status(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Occasionally transition between logistics lifecycle states."""
    if random.random() < 0.002:
        state.transport_status = random.choice(constraints.transport_statuses)


def advance_container(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Apply all telemetry updates for one simulation tick."""
    update_temperature(state, constraints)
    update_humidity(state, constraints)
    update_battery(state, constraints)
    update_position(state, constraints)
    update_vibration(state, constraints)
    update_transport_status(state, constraints)
    state.tick += 1


def build_event(state: ContainerState) -> dict:
    """Build a schema-compliant sensor event dict from the current container state."""
    return {
        "container_id": state.container_id,
        "shipment_id": state.shipment_id,
        "commodity_name": state.commodity_name,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "latitude": round(state.latitude, 6),
        "longitude": round(state.longitude, 6),
        "temperature": round(state.temperature, 2),
        "humidity": round(state.humidity, 2),
        "vibration": round(state.vibration, 3),
        "battery_level": round(state.battery_level, 2),
        "transport_status": state.transport_status,
    }


def print_event(event: dict) -> None:
    """Print a single sensor event as formatted JSON to the terminal."""
    print(json.dumps(event, indent=2))
    print("-" * 60)


def run_simulation(
    container_count: int = 20,
    interval_seconds: float = 1.0,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> None:
    """
    Run the IoT simulator continuously until interrupted (Ctrl+C).

    Generates one event per container every `interval_seconds`.
    """
    schema = load_schema(schema_path)
    constraints = parse_schema_constraints(schema)
    fleet = initialize_fleet(container_count, constraints)

    print(f"Starting AtmoSync IoT simulator — {container_count} containers, {interval_seconds}s interval")
    print(f"Schema: {schema_path}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            for container in fleet:
                advance_container(container, constraints)
                print_event(build_event(container))
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")


def main() -> None:
    """Entry point: load env overrides and start the simulation."""
    load_dotenv(PROJECT_ROOT / ".env")

    container_count = int(os.getenv("SIMULATOR_DEVICE_COUNT", "20"))
    interval_seconds = float(os.getenv("SIMULATOR_INTERVAL_SECONDS", "1"))

    run_simulation(
        container_count=container_count,
        interval_seconds=interval_seconds,
    )


if __name__ == "__main__":
    main()
