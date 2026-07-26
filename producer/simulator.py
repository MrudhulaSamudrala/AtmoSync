"""
AtmoSync IoT sensor simulator for agricultural shipping containers.

Generates continuous JSON sensor events conforming to config/sensor_schema.json.
"""

from __future__ import annotations

import json
import math
import random
import string
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import os

from commodity_config import (
    Commodity,
    DEFAULT_COMMODITIES_PATH,
    assign_commodity,
    get_simulation_profile,
    load_commodities,
)
from health_score import calculate_health_score
from spoilage import (
    calculate_remaining_shelf_life_days,
    classify_spoilage_risk,
    estimate_spoilage_metrics,
)

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

# Anomaly types and trigger probability range (1–3% per update when normal).
ANOMALY_TYPES = (
    "temperature_spike",
    "humidity_spike",
    "heavy_vibration",
    "battery_failure",
)
ANOMALY_TRIGGER_PROB_MIN = 0.01
ANOMALY_TRIGGER_PROB_MAX = 0.03


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
    commodity_id: str
    commodity_name: str
    commodity: Commodity
    latitude: float
    longitude: float
    temperature: float
    humidity: float
    vibration: float
    battery_level: float
    transport_status: str
    heading: float  # movement bearing in radians
    tick: int = 0
    anomaly_type: str = "normal"
    anomaly_active_remaining: int = 0
    anomaly_recovery_remaining: int = 0
    anomaly_recovery_ticks: int = 0
    saved_battery_level: float | None = None
    spoilage_percentage: float = 0.0


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


def create_container_state(
    constraints: SchemaConstraints,
    commodities: list[Commodity],
) -> ContainerState:
    """Initialize a single container with realistic starting telemetry."""
    commodity = assign_commodity(commodities)
    profile = get_simulation_profile(commodity)
    origin_lat, origin_lng = random.choice(ROUTE_ORIGINS)

    # Scatter containers near their route origin.
    latitude = origin_lat + random.uniform(-0.5, 0.5)
    longitude = origin_lng + random.uniform(-0.5, 0.5)

    return ContainerState(
        container_id=generate_container_id(),
        shipment_id=generate_shipment_id(),
        commodity_id=commodity.commodity_id,
        commodity_name=commodity.commodity_name,
        commodity=commodity,
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


def initialize_fleet(
    count: int,
    constraints: SchemaConstraints,
    commodities: list[Commodity],
) -> list[ContainerState]:
    """Create the full set of simulated containers."""
    return [create_container_state(constraints, commodities) for _ in range(count)]


def update_temperature(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Drift temperature around the commodity target with small random noise."""
    profile = get_simulation_profile(state.commodity)
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
    profile = get_simulation_profile(state.commodity)
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


def maybe_generate_anomaly(state: ContainerState) -> None:
    """Randomly trigger a new anomaly when the container is in a normal state."""
    if state.anomaly_type != "normal":
        return

    trigger_probability = random.uniform(ANOMALY_TRIGGER_PROB_MIN, ANOMALY_TRIGGER_PROB_MAX)
    if random.random() >= trigger_probability:
        return

    anomaly_type = random.choice(ANOMALY_TYPES)
    state.anomaly_type = anomaly_type
    state.anomaly_active_remaining = random.randint(15, 45)
    state.anomaly_recovery_remaining = 0
    state.anomaly_recovery_ticks = random.randint(20, 60)

    if anomaly_type == "battery_failure":
        state.saved_battery_level = state.battery_level


def get_anomaly_intensity(state: ContainerState) -> float:
    """
    Return the current anomaly effect strength.

    1.0 during the active phase; linearly decays to 0.0 over the recovery phase.
    """
    if state.anomaly_type == "normal":
        return 0.0
    if state.anomaly_active_remaining > 0:
        return 1.0
    if state.anomaly_recovery_remaining > 0 and state.anomaly_recovery_ticks > 0:
        return state.anomaly_recovery_remaining / state.anomaly_recovery_ticks
    return 0.0


def apply_anomaly_temperature_spike(
    state: ContainerState,
    constraints: SchemaConstraints,
    intensity: float,
) -> None:
    """Push temperature well above the cold-chain setpoint during a spike event."""
    profile = get_simulation_profile(state.commodity)
    spike = random.uniform(8.0, 15.0) * intensity
    state.temperature = clamp(
        profile["temp"] + spike,
        constraints.temp_min,
        constraints.temp_max,
    )


def apply_anomaly_humidity_spike(
    state: ContainerState,
    constraints: SchemaConstraints,
    intensity: float,
) -> None:
    """Push humidity toward saturation during a condensation / seal-failure event."""
    spike = random.uniform(5.0, 12.0) * intensity
    state.humidity = clamp(
        state.humidity + spike,
        constraints.humidity_min,
        constraints.humidity_max,
    )


def apply_anomaly_heavy_vibration(
    state: ContainerState,
    constraints: SchemaConstraints,
    intensity: float,
) -> None:
    """Simulate impact or rough-handling vibration well above normal transit levels."""
    heavy_level = random.uniform(2.5, 4.5) * intensity + random.uniform(0.05, 0.2)
    state.vibration = clamp(heavy_level, constraints.vibration_min, constraints.vibration_max)


def apply_anomaly_battery_failure(
    state: ContainerState,
    constraints: SchemaConstraints,
    intensity: float,
) -> None:
    """Simulate rapid battery depletion during a sensor power fault."""
    if intensity >= 0.95:
        target = random.uniform(2.0, 8.0)
    else:
        saved = state.saved_battery_level if state.saved_battery_level is not None else 50.0
        target = saved * (1.0 - intensity) + random.uniform(2.0, 8.0) * intensity
    state.battery_level = clamp(target, constraints.battery_min, constraints.battery_max)


def apply_anomaly_effects(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Apply the sensor distortion matching the active anomaly type."""
    intensity = get_anomaly_intensity(state)
    if intensity <= 0:
        return

    if state.anomaly_type == "temperature_spike":
        apply_anomaly_temperature_spike(state, constraints, intensity)
    elif state.anomaly_type == "humidity_spike":
        apply_anomaly_humidity_spike(state, constraints, intensity)
    elif state.anomaly_type == "heavy_vibration":
        apply_anomaly_heavy_vibration(state, constraints, intensity)
    elif state.anomaly_type == "battery_failure":
        apply_anomaly_battery_failure(state, constraints, intensity)


def recover_from_anomaly(state: ContainerState, constraints: SchemaConstraints) -> None:
    """Gradually pull affected sensors back toward normal during the recovery phase."""
    if state.anomaly_active_remaining > 0 or state.anomaly_type == "normal":
        return

    intensity = get_anomaly_intensity(state)
    if intensity <= 0:
        return

    profile = get_simulation_profile(state.commodity)
    recovery_strength = 0.12 * (1.0 - intensity)

    if state.anomaly_type == "temperature_spike":
        state.temperature += (profile["temp"] - state.temperature) * recovery_strength
        state.temperature = clamp(state.temperature, constraints.temp_min, constraints.temp_max)

    elif state.anomaly_type == "humidity_spike":
        state.humidity += (profile["humidity"] - state.humidity) * recovery_strength
        state.humidity = clamp(state.humidity, constraints.humidity_min, constraints.humidity_max)

    elif state.anomaly_type == "heavy_vibration":
        normal_vibration = random.uniform(0.05, 0.25)
        state.vibration += (normal_vibration - state.vibration) * recovery_strength
        state.vibration = clamp(state.vibration, constraints.vibration_min, constraints.vibration_max)

    elif state.anomaly_type == "battery_failure" and state.saved_battery_level is not None:
        state.battery_level += (state.saved_battery_level - state.battery_level) * recovery_strength * 0.5
        state.battery_level = clamp(state.battery_level, constraints.battery_min, constraints.battery_max)


def advance_anomaly_lifecycle(state: ContainerState) -> None:
    """Decrement anomaly timers and reset state when recovery completes."""
    if state.anomaly_type == "normal":
        return

    if state.anomaly_active_remaining > 0:
        state.anomaly_active_remaining -= 1
        if state.anomaly_active_remaining == 0:
            state.anomaly_recovery_remaining = state.anomaly_recovery_ticks
        return

    if state.anomaly_recovery_remaining > 0:
        state.anomaly_recovery_remaining -= 1
        if state.anomaly_recovery_remaining == 0:
            state.anomaly_type = "normal"
            state.saved_battery_level = None


def update_spoilage(
    state: ContainerState,
    interval_seconds: float,
) -> None:
    """Advance cumulative spoilage based on current sensors and health score."""
    health_score = calculate_health_score(
        state.commodity,
        state.temperature,
        state.humidity,
        state.vibration,
        state.battery_level,
    )
    metrics = estimate_spoilage_metrics(
        state.commodity,
        state.temperature,
        state.humidity,
        health_score,
        state.spoilage_percentage,
        interval_seconds,
    )
    state.spoilage_percentage = float(metrics["spoilage_percentage"])


def advance_container(
    state: ContainerState,
    constraints: SchemaConstraints,
    interval_seconds: float = 1.0,
) -> None:
    """Apply all telemetry updates for one simulation tick."""
    maybe_generate_anomaly(state)
    update_temperature(state, constraints)
    update_humidity(state, constraints)
    update_battery(state, constraints)
    update_position(state, constraints)
    update_vibration(state, constraints)
    update_transport_status(state, constraints)
    apply_anomaly_effects(state, constraints)
    recover_from_anomaly(state, constraints)
    advance_anomaly_lifecycle(state)
    update_spoilage(state, interval_seconds)
    state.tick += 1


def build_event(state: ContainerState) -> dict:
    """Build a schema-compliant sensor event dict from the current container state."""
    health_score = calculate_health_score(
        state.commodity,
        state.temperature,
        state.humidity,
        state.vibration,
        state.battery_level,
    )

    return {
        "container_id": state.container_id,
        "shipment_id": state.shipment_id,
        "commodity_id": state.commodity_id,
        "commodity_name": state.commodity_name,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "latitude": round(state.latitude, 6),
        "longitude": round(state.longitude, 6),
        "temperature": round(state.temperature, 2),
        "humidity": round(state.humidity, 2),
        "vibration": round(state.vibration, 3),
        "battery_level": round(state.battery_level, 2),
        "transport_status": state.transport_status,
        "anomaly_type": state.anomaly_type,
        "health_score": health_score,
        "spoilage_percentage": state.spoilage_percentage,
        "remaining_shelf_life_days": calculate_remaining_shelf_life_days(
            state.commodity,
            state.spoilage_percentage,
        ),
        "spoilage_risk_level": classify_spoilage_risk(state.spoilage_percentage),
    }


def print_event(event: dict) -> None:
    """Print a single sensor event as formatted JSON to the terminal."""
    print(json.dumps(event, indent=2))
    print("-" * 60)


def create_kafka_producer():
    """Initialize the Kafka producer, returning None when Kafka is unavailable."""
    try:
        import importlib.util

        module_path = PROJECT_ROOT / "kafka" / "producer.py"
        spec = importlib.util.spec_from_file_location("atmosync_kafka_producer", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load Kafka producer module from {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        KafkaProducer = module.KafkaProducer

        producer = KafkaProducer()
        if producer.connect():
            return producer

        print(
            f"Warning: Kafka unavailable ({producer.last_error}); "
            "continuing with console output only."
        )
    except Exception as exc:
        print(f"Warning: Kafka producer could not be initialized ({exc}); continuing with console output only.")

    return None


def run_simulation(
    container_count: int = 20,
    interval_seconds: float = 1.0,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    commodities_path: Path = DEFAULT_COMMODITIES_PATH,
) -> None:
    """
    Run the IoT simulator continuously until interrupted (Ctrl+C).

    Generates one event per container every `interval_seconds`.
    """
    schema = load_schema(schema_path)
    constraints = parse_schema_constraints(schema)
    commodities = load_commodities(commodities_path)
    fleet = initialize_fleet(container_count, constraints, commodities)
    kafka_producer = create_kafka_producer()

    print(f"Starting AtmoSync IoT simulator — {container_count} containers, {interval_seconds}s interval")
    print(f"Schema: {schema_path}")
    print(f"Commodities: {commodities_path} ({len(commodities)} loaded)")
    if kafka_producer is not None:
        print("Kafka publishing: enabled")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            for container in fleet:
                advance_container(container, constraints, interval_seconds)
                event = build_event(container)
                print_event(event)
                if kafka_producer is not None:
                    kafka_producer.send_event(event)
            if kafka_producer is not None:
                kafka_producer.flush(timeout=5)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    finally:
        if kafka_producer is not None:
            kafka_producer.close()


def main() -> None:
    """Entry point: load env overrides and start the simulation."""
    load_dotenv(PROJECT_ROOT / ".env")

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    container_count = int(os.getenv("SIMULATOR_DEVICE_COUNT", "20"))
    interval_seconds = float(os.getenv("SIMULATOR_INTERVAL_SECONDS", "1"))

    run_simulation(
        container_count=container_count,
        interval_seconds=interval_seconds,
    )


if __name__ == "__main__":
    main()
