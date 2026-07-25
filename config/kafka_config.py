"""
Kafka connection and client configuration for AtmoSync streaming.

Bootstrap servers, topic names, and producer/consumer settings are loaded from
environment variables (see .env.example). Actual Kafka clients will be implemented
in kafka/producer.py and kafka/consumer.py.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Connection & topic
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC: str = os.getenv("KAFKA_TOPIC", "atmosync.sensor.readings")

# ---------------------------------------------------------------------------
# Producer configuration
# ---------------------------------------------------------------------------

KAFKA_PRODUCER_CONFIG: dict[str, str | int | float | bool] = {
    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
    "acks": os.getenv("KAFKA_PRODUCER_ACKS", "all"),
    "retries": int(os.getenv("KAFKA_PRODUCER_RETRIES", "3")),
    "linger.ms": int(os.getenv("KAFKA_PRODUCER_LINGER_MS", "5")),
    "batch.size": int(os.getenv("KAFKA_PRODUCER_BATCH_SIZE", "16384")),
    "compression.type": os.getenv("KAFKA_PRODUCER_COMPRESSION", "snappy"),
    "client.id": os.getenv("KAFKA_PRODUCER_CLIENT_ID", "atmosync-producer"),
}

# ---------------------------------------------------------------------------
# Consumer configuration
# ---------------------------------------------------------------------------

KAFKA_CONSUMER_CONFIG: dict[str, str | int | float | bool] = {
    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
    "group.id": os.getenv("KAFKA_CONSUMER_GROUP_ID", "atmosync-consumer"),
    "auto.offset.reset": os.getenv("KAFKA_CONSUMER_AUTO_OFFSET_RESET", "earliest"),
    "enable.auto.commit": os.getenv("KAFKA_CONSUMER_ENABLE_AUTO_COMMIT", "true").lower()
    == "true",
    "session.timeout.ms": int(os.getenv("KAFKA_CONSUMER_SESSION_TIMEOUT_MS", "10000")),
    "client.id": os.getenv("KAFKA_CONSUMER_CLIENT_ID", "atmosync-consumer"),
}
