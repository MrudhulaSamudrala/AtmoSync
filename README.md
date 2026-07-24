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
├── scripts/        # Utility and deployment scripts
└── logs/           # Runtime log output (gitignored)
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

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
