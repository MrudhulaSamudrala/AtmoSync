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
├── kafka/          # Kafka producer and consumer modules
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

## Step 4 - Commodity Configuration

- Added commodity master dataset.
- Supports five agricultural commodities.
- Commodity information is loaded from datasets/commodities.csv.
- Containers are assigned commodities during initialization.
- Sensor values are generated according to commodity-specific storage conditions.

## Step 5 - Anomaly Simulation

- Added realistic anomaly generation.
- Simulated temperature spikes.
- Simulated humidity spikes.
- Simulated heavy vibration events.
- Simulated battery failures.
- Added `anomaly_type` field to telemetry events.

## Step 6 - Spoilage Estimation

- Added spoilage percentage calculation.
- Added remaining shelf life estimation.
- Added spoilage risk classification.
- Spoilage uses health score and commodity properties.
- New spoilage fields included in every telemetry event.

## Step 7 - Kafka Infrastructure

- Prepared Kafka configuration.
- Added environment configuration.
- Created producer and consumer modules.
- Project ready for Kafka integration.

## Step 8 - Kafka Producer

The simulator now publishes every generated telemetry event to Kafka in addition to printing it to the console.

### How the producer works

`kafka/producer.py` defines a reusable `KafkaProducer` wrapper around **kafka-python**. On startup the simulator calls `connect()`, which builds a client from `config/kafka_config.py` (bootstrap servers, acks, retries, batching, compression, and client ID). Each event is sent with `send_event()`, batched asynchronously by kafka-python, then `flush()` ensures delivery before the next simulation interval. On shutdown, `close()` flushes remaining messages and releases the client.

If Kafka is unreachable or misconfigured, connection and send failures are caught and logged; the simulator prints a warning and continues emitting events to the console only.

### Why `container_id` is the message key

Kafka routes messages with the same key to the same topic partition. Using `container_id` as the key keeps all readings for one shipping container ordered on a single partition, which preserves per-container time series for downstream consumers (Snowflake pipes, anomaly detection, spoilage dashboards) without cross-partition reordering.

### JSON serialization

Each telemetry dict is serialized with `json.dumps()` and encoded as UTF-8 bytes before publish. The payload matches the existing sensor schema (`config/sensor_schema.json`) — the same structure already printed to the console — so consumers can deserialize JSON directly without an extra schema registry step at this stage.

### Event flow

```
producer/simulator.py
    │
    ├─ advance_container() / build_event()   ← telemetry, health, anomaly, spoilage (unchanged)
    │
    ├─ print_event()                       → stdout (JSON)
    │
    └─ KafkaProducer.send_event()          → Kafka topic (KAFKA_TOPIC)
           key: container_id
           value: JSON event
```

Ensure Kafka is running and `.env` contains valid `KAFKA_BOOTSTRAP_SERVERS` and `KAFKA_TOPIC` values, then run:

```bash
python producer/simulator.py
```

## Kafka Producer Validation

- Verified connection to Kafka broker.
- Verified telemetry events are published.
- Added publish success logging.
- Added publish failure logging.

When the broker is reachable, the producer logs a successful connection on startup. After each acknowledged publish, it logs the **topic**, **partition**, **offset**, and **container_id**. Publish failures are logged with the error and `container_id`; the simulator keeps running and JSON events continue to print to the console for debugging.

### Partition and offset

A Kafka **topic** is split into **partitions** — ordered, append-only logs. Messages with the same key (`container_id`) land on the same partition, so readings for one container stay in order. Each message within a partition receives a monotonically increasing **offset** — its permanent position in that partition. Offsets let consumers resume from a known point and confirm that a specific record was stored.

### How Kafka acknowledges a message

The producer sends a batch to the broker leader for the target partition. With `acks=all` (the default in `config/kafka_config.py`), the broker waits until the record is committed to the partition log (and replicated per cluster settings) before replying. kafka-python surfaces that reply as `RecordMetadata` (topic, partition, offset). The producer's success callback runs only after that acknowledgement — confirming the event is durably written, not merely queued locally.

### Verify events are stored in Kafka

1. Start the broker (for example with Docker Compose):

```bash
docker compose up -d
```

2. Run the simulator and watch for `Successfully connected to Kafka broker` and `Kafka publish succeeded` log lines.

3. Read messages back from the topic:

```bash
docker exec -it atmosync-kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic atmosync.sensor.readings \
  --from-beginning \
  --property print.key=true \
  --property key.separator=" | "
```

You should see each message key (`container_id`) paired with the JSON telemetry payload. Offsets in the producer logs correspond to the records visible to this consumer.

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
