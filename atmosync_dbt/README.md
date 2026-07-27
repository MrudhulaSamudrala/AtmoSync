# AtmoSync dbt Project

Independent dbt transformation layer for the AtmoSync cold-chain telemetry platform. This project reads raw sensor events already stored in Snowflake and builds analytics-ready staging, dimension, and fact models.

**This project does not modify the Python ingestion pipeline.** Kafka, the consumer, and Snowflake ingestion remain unchanged.

---

## 1. Purpose of dbt

[dbt](https://www.getdbt.com/) (data build tool) transforms data inside your warehouse using version-controlled SQL. It provides:

- **Modular SQL models** — reusable, testable transformations
- **Dependency management** — `ref()` and `source()` track lineage automatically
- **Data quality tests** — `unique`, `not_null`, `accepted_values`, `relationships`
- **Documentation** — auto-generated docs from `schema.yml` files

AtmoSync uses dbt to turn append-only RAW telemetry into clean tables that Apache Superset and other BI tools can query safely.

---

## 2. RAW vs Analytics Tables

| Layer | Schema | Purpose |
|-------|--------|---------|
| **RAW** | `RAW` | Exact copy of streamed events; append-only audit trail |
| **Staging** | `STAGING` | Typed, renamed, lightly cleaned — one row per event |
| **Dimensions** | `DIMENSIONS` | Descriptive reference data (e.g. commodities) |
| **Facts** | `FACTS` | Measurable events for dashboards and analysis |

RAW tables prioritize ingestion speed and completeness. Analytics tables prioritize correctness, consistency, and usability for business users.

---

## 3. Model Hierarchy

```
RAW (RAW_SENSOR_EVENTS)
 ↓
STAGING (stg_sensor_events)
 ↓
DIMENSIONS (dim_commodity)
 ↓
FACTS (fact_container_health, fact_spoilage)
```

### Models

| Model | Schema | Description |
|-------|--------|-------------|
| `stg_sensor_events` | `STAGING` | Cleaned, typed telemetry — one row per event |
| `dim_commodity` | `DIMENSIONS` | One row per commodity (deduplicated) |
| `fact_container_health` | `FACTS` | Environmental + health metrics per event |
| `fact_spoilage` | `FACTS` | Spoilage metrics per event, linked to commodities |

---

## Setup

### Prerequisites

- Python 3.9+
- [dbt Core](https://docs.getdbt.com/docs/core/installation-overview) with the [Snowflake adapter](https://docs.getdbt.com/docs/core/connect-data-platform/snowflake-setup)
- Snowflake credentials (same `SNOWFLAKE_*` variables used by the ingestion pipeline)
- Live data in `ATMOSYNC_DB.RAW.RAW_SENSOR_EVENTS`

### Install dbt

```bash
pip install dbt-snowflake
```

### Configure connection

1. Copy the example profile:

```bash
cd atmosync_dbt
copy profiles.yml.example profiles.yml
```

2. Set environment variables (PowerShell example):

```powershell
$env:DBT_PROFILES_DIR = "C:\Users\User\AtmoSync\atmosync_dbt"
$env:SNOWFLAKE_ACCOUNT = "your_account"
$env:SNOWFLAKE_USER = "your_user"
$env:SNOWFLAKE_PASSWORD = "your_password"
$env:SNOWFLAKE_WAREHOUSE = "ATMOSYNC_WH"
$env:SNOWFLAKE_DATABASE = "ATMOSYNC_DB"
$env:SNOWFLAKE_SCHEMA = "RAW"
$env:SNOWFLAKE_ROLE = "your_role"
```

Credentials are never hardcoded — they are read from environment variables at runtime.

3. Install dbt packages:

```bash
dbt deps
```

---

## 4. Commands

Run all commands from the `atmosync_dbt/` directory.

### Verify connection

```bash
dbt debug
```

### Build all models

```bash
dbt run
```

Creates tables in `STAGING`, `DIMENSIONS`, and `FACTS` schemas.

### Run data quality tests

```bash
dbt test
```

Tests RAW source freshness, column constraints, uniqueness, and referential integrity between facts and dimensions.

### Generate documentation

```bash
dbt docs generate
dbt docs serve
```

Opens a local docs site with model lineage, column descriptions, and test coverage.

---

## Project Structure

```
atmosync_dbt/
├── dbt_project.yml
├── packages.yml
├── profiles.yml.example
├── models/
│   ├── sources.yml
│   ├── staging/
│   │   ├── stg_sensor_events.sql
│   │   └── schema.yml
│   └── marts/
│       ├── dimensions/
│       │   ├── dim_commodity.sql
│       │   └── schema.yml
│       └── facts/
│           ├── fact_container_health.sql
│           ├── fact_spoilage.sql
│           └── schema.yml
├── macros/
│   └── generate_schema_name.sql
├── tests/
├── snapshots/
├── seeds/
└── README.md
```

---

## End-to-End Architecture

```
IoT Simulator
      ↓
Kafka Producer
      ↓
Kafka Broker
      ↓
Kafka Consumer
      ↓
Snowflake RAW_SENSOR_EVENTS
      ↓
dbt Staging
      ↓
Dimension Models
      ↓
Fact Models
      ↓
Apache Superset
```

---

## Tests

| Target | Tests applied |
|--------|---------------|
| `RAW_SENSOR_EVENTS` (source) | `not_null`, `accepted_values`, unique grain |
| `stg_sensor_events` | `not_null`, `accepted_values`, unique grain |
| `dim_commodity` | `unique`, `not_null`, `accepted_values` |
| `fact_container_health` | `not_null`, `accepted_values`, unique grain |
| `fact_spoilage` | `not_null`, `accepted_values`, `relationships` → `dim_commodity` |
