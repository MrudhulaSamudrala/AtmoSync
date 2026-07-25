# AtmoSync: Micro-Climate Arbitrage Analytics

AtmoSync is a data engineering platform that ingests micro-climate sensor data, models environmental conditions across locations, and surfaces arbitrage opportunities—situations where small geographic or temporal climate differences can inform operational or commercial decisions.

## Project Structure

```
AtmoSync/
├── producer/       # Data producers (IoT simulator, later ingest pipelines)
├── consumer/       # Downstream consumers (analytics, alerts, exports)
├── datasets/       # Local raw and sample datasets
├── snowflake/      # Snowflake DDL, stages, pipes, and roles
├── dbt/            # dbt models, seeds, and macros
├── superset/       # BI dashboards and dataset definitions
├── docs/           # Architecture, runbooks, and project documentation
├── tests/          # Automated tests
├── config/         # Application and environment configuration
└── scripts/        # Utility and deployment scripts

```

## Setup

```bash
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Copy the environment template and adjust values as needed:

```bash
cp .env.example .env
```

## Step 2 - IoT Sensor Schema

- Designed the IoT event schema for refrigerated agricultural shipping containers (`config/sensor_schema.json`).
- Fields: `container_id`, `shipment_id`, `commodity_name`, `timestamp`, `latitude`, `longitude`, `temperature`, `humidity`, `vibration`, `battery_level`, `transport_status`.
- Purpose: define a consistent, validated event contract for streaming sensor data through Kafka, Snowflake, and downstream analytics.
- Added sample JSON event in the schema `examples` block (avocado shipment in transit, Mexico City coordinates).

## Step 3 - IoT Simulator

- Built a Python IoT simulator (`producer/simulator.py`).
- Simulates 20 agricultural shipping containers.
- Generates one JSON event every second.
- Produces realistic telemetry data (commodity-based temperature/humidity, GPS drift, battery drain, vibration).
- Uses the previously designed sensor schema for field enums and value ranges.

Run the simulator:

```bash
python producer/simulator.py
```

## Step 4 - Anomaly Simulation

- Added realistic anomaly generation.
- Simulated temperature spikes.
- Simulated humidity spikes.
- Simulated heavy vibration events.
- Simulated battery failures.
- Added `anomaly_type` field to telemetry events.

## Documentation

<!-- TODO: Add architecture overview -->
<!-- TODO: Add data dictionary -->
<!-- TODO: Add deployment runbook -->
<!-- TODO: Add development guide -->

## Roadmap

1. **IoT simulator** — Generate realistic micro-climate sensor streams
2. **Streaming** — Apache Kafka for event ingestion
3. **Warehouse** — Snowflake for storage and compute
4. **Transform** — dbt for curated analytics models
5. **Visualize** — Apache Superset for dashboards and arbitrage insights
