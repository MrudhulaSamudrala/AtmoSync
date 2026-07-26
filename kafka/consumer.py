"""
Kafka consumer for AtmoSync telemetry events.

Wraps kafka-python to subscribe to the configured topic, deserialize JSON sensor
events, validate them, and process each event through a dedicated handler.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.kafka_config import KAFKA_CONSUMER_CONFIG, KAFKA_TOPIC

logger = logging.getLogger(__name__)

# Required telemetry fields from config/sensor_schema.json.
REQUIRED_TELEMETRY_FIELDS: frozenset[str] = frozenset(
    {
        "container_id",
        "shipment_id",
        "commodity_id",
        "commodity_name",
        "timestamp",
        "latitude",
        "longitude",
        "temperature",
        "humidity",
        "vibration",
        "battery_level",
        "transport_status",
        "anomaly_type",
        "health_score",
        "spoilage_percentage",
        "remaining_shelf_life_days",
        "spoilage_risk_level",
    }
)


def _configure_logging() -> None:
    """Ensure consumer logs are visible when no logging setup exists."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )


_CONFLUENT_TO_KAFKA_PYTHON = {
    "bootstrap.servers": "bootstrap_servers",
    "group.id": "group_id",
    "auto.offset.reset": "auto_offset_reset",
    "enable.auto.commit": "enable_auto_commit",
    "session.timeout.ms": "session_timeout_ms",
    "client.id": "client_id",
}


def _load_kafka_consumer_client():
    """
    Import KafkaConsumer from kafka-python.

    The local kafka/ package shadows the installed kafka-python module when the
    project root is on sys.path, so the project root is temporarily removed
    during import.
    """
    project_root = str(PROJECT_ROOT.resolve())
    saved_path = sys.path.copy()
    sys.path = [entry for entry in sys.path if Path(entry).resolve() != PROJECT_ROOT.resolve()]

    stale_modules = [
        name
        for name, module in sys.modules.items()
        if name == "kafka" or name.startswith("kafka.")
        if (getattr(module, "__file__", None) and project_root in module.__file__.replace("\\", "/"))
    ]
    for name in stale_modules:
        del sys.modules[name]

    try:
        from kafka import KafkaConsumer as KafkaConsumerClient

        return KafkaConsumerClient
    finally:
        sys.path = saved_path


def _is_empty_config_value(value: Any) -> bool:
    """Return True for None or blank strings that must not be passed to kafka-python."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def _build_consumer_kwargs(config: dict[str, str | int | float | bool]) -> dict[str, Any]:
    """Translate config.kafka_config consumer settings to kafka-python parameters."""
    kwargs: dict[str, Any] = {}
    for key, value in config.items():
        if _is_empty_config_value(value):
            continue

        param_name = _CONFLUENT_TO_KAFKA_PYTHON.get(key, key)
        kwargs[param_name] = value

    bootstrap_servers = kwargs.get("bootstrap_servers")
    if isinstance(bootstrap_servers, str):
        kwargs["bootstrap_servers"] = [
            server.strip()
            for server in bootstrap_servers.split(",")
            if server.strip()
        ]

    return kwargs


class KafkaConsumer:
    """Reusable wrapper around kafka-python for consuming telemetry events."""

    def __init__(
        self,
        topic: str = KAFKA_TOPIC,
        config: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        self._topic = topic
        self._config = dict(config or KAFKA_CONSUMER_CONFIG)
        self._client: Any | None = None
        self._client_cls: Any | None = None
        self._connected = False
        self._last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self._connected and self._client is not None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def connect(self) -> bool:
        """Create the underlying kafka-python consumer and subscribe to the topic."""
        if self._connected and self._client is not None:
            return True

        _configure_logging()

        try:
            if self._client_cls is None:
                self._client_cls = _load_kafka_consumer_client()

            kwargs = _build_consumer_kwargs(self._config)
            self._client = self._client_cls(**kwargs)
            self._client.subscribe([self._topic])

            self._connected = True
            self._last_error = None
            logger.info(
                "Successfully connected to Kafka broker (bootstrap=%s, group=%s)",
                self._config.get("bootstrap.servers"),
                self._config.get("group.id"),
            )
            logger.info("Subscribed to topic: %s", self._topic)
            return True
        except Exception as exc:
            self._connected = False
            self._last_error = str(exc)
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
            logger.warning("Kafka connection failed: %s", exc)
            return False

    def consume_events(self) -> None:
        """Continuously consume messages from the subscribed topic."""
        if not self.connected and not self.connect():
            raise ConnectionError(self._last_error or "Kafka consumer is not connected")

        logger.info("Consumer started — waiting for telemetry events on topic %s", self._topic)

        try:
            for message in self._client:
                self._handle_message(message)
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
            raise

    def _handle_message(self, message: Any) -> None:
        """Deserialize, validate, and dispatch a single Kafka message."""
        container_hint = message.key.decode("utf-8") if message.key else "unknown"

        logger.info(
            "Event received: topic=%s partition=%s offset=%s key=%s",
            message.topic,
            message.partition,
            message.offset,
            container_hint,
        )

        if message.value is None:
            logger.warning(
                "Event validation failed: null message value at partition=%s offset=%s",
                message.partition,
                message.offset,
            )
            return

        try:
            event = json.loads(message.value.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning(
                "JSON decode failed: partition=%s offset=%s error=%s",
                message.partition,
                message.offset,
                exc,
            )
            return

        if not self._validate_event(event, message.partition, message.offset):
            return

        try:
            self.process_event(event)
        except Exception as exc:
            logger.warning(
                "Event processing failed: container_id=%s error=%s",
                event.get("container_id", container_hint),
                exc,
            )

    def _validate_event(self, event: Any, partition: int, offset: int) -> bool:
        """Return True when the event contains all required telemetry fields."""
        if not isinstance(event, dict):
            logger.warning(
                "Event validation failed: expected JSON object at partition=%s offset=%s",
                partition,
                offset,
            )
            return False

        missing_fields = sorted(field for field in REQUIRED_TELEMETRY_FIELDS if field not in event)
        if missing_fields:
            logger.warning(
                "Event validation failed: missing fields %s at partition=%s offset=%s",
                missing_fields,
                partition,
                offset,
            )
            return False

        return True

    def process_event(self, event: dict) -> None:
        """Handle a validated telemetry event (print for development; Snowflake next)."""
        # ------------------------------------------------------------------
        # TODO (Step 10 — Snowflake ingestion):
        # Insert the validated `event` dict into a Snowflake staging table here.
        # Example: snowflake_loader.insert_telemetry(event)
        # ------------------------------------------------------------------

        print(
            "\n--- Telemetry Event ---\n"
            f"Container:  {event['container_id']} | Shipment: {event['shipment_id']}\n"
            f"Commodity:  {event['commodity_name']} ({event['commodity_id']})\n"
            f"Timestamp:  {event['timestamp']}\n"
            f"Location:   {event['latitude']}, {event['longitude']}\n"
            f"Readings:   temp={event['temperature']} °C  "
            f"humidity={event['humidity']}%  "
            f"vibration={event['vibration']} g  "
            f"battery={event['battery_level']}%\n"
            f"Status:     {event['transport_status']}  "
            f"anomaly={event['anomaly_type']}\n"
            f"Health:     score={event['health_score']}  "
            f"spoilage={event['spoilage_percentage']}%  "
            f"shelf_life={event['remaining_shelf_life_days']} days  "
            f"risk={event['spoilage_risk_level']}\n"
            f"{'-' * 23}"
        )

    def close(self) -> None:
        """Close the consumer and release broker resources."""
        if self._client is None:
            return

        try:
            self._client.close()
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Kafka close failed: %s", exc)
        finally:
            self._client = None
            self._connected = False
            logger.info("Shutdown completed")


def main() -> None:
    """Entry point: connect to Kafka and consume telemetry events until interrupted."""
    _configure_logging()
    consumer = KafkaConsumer()

    try:
        if not consumer.connect():
            logger.error("Kafka unavailable: %s", consumer.last_error)
            sys.exit(1)

        consumer.consume_events()
    except KeyboardInterrupt:
        logger.info("Stopping consumer...")
    except ConnectionError as exc:
        logger.error("Kafka unavailable: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected consumer error: %s", exc)
        sys.exit(1)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
