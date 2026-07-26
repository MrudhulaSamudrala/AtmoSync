"""
Kafka producer for AtmoSync telemetry events.

Wraps kafka-python to publish JSON sensor events using settings from
config.kafka_config.
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

from config.kafka_config import KAFKA_PRODUCER_CONFIG, KAFKA_TOPIC

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Ensure producer validation logs are visible when the simulator has no logging setup."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )


_CONFLUENT_TO_KAFKA_PYTHON = {
    "bootstrap.servers": "bootstrap_servers",
    "linger.ms": "linger_ms",
    "batch.size": "batch_size",
    "compression.type": "compression_type",
    "client.id": "client_id",
}


def _load_kafka_producer_client():
    """
    Import KafkaProducer from kafka-python.

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
        from kafka import KafkaProducer as KafkaProducerClient

        return KafkaProducerClient
    finally:
        sys.path = saved_path


def _build_producer_kwargs(config: dict[str, str | int | float | bool]) -> dict[str, Any]:
    """Translate config.kafka_config producer settings to kafka-python parameters."""
    kwargs: dict[str, Any] = {}
    for key, value in config.items():
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


class KafkaProducer:
    """Reusable wrapper around kafka-python for publishing telemetry events."""

    def __init__(
        self,
        topic: str = KAFKA_TOPIC,
        config: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        self._topic = topic
        self._config = dict(config or KAFKA_PRODUCER_CONFIG)
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
        """Create the underlying kafka-python producer. Returns False on failure."""
        if self._connected and self._client is not None:
            return True

        _configure_logging()

        try:
            if self._client_cls is None:
                self._client_cls = _load_kafka_producer_client()

            kwargs = _build_producer_kwargs(self._config)
            kwargs["key_serializer"] = lambda key: key.encode("utf-8") if key is not None else None
            kwargs["value_serializer"] = lambda value: json.dumps(value, separators=(",", ":")).encode(
                "utf-8"
            )

            self._client = self._client_cls(**kwargs)
            self._connected = True
            self._last_error = None
            logger.info(
                "Successfully connected to Kafka broker (bootstrap=%s, topic=%s)",
                self._config.get("bootstrap.servers"),
                self._topic,
            )
            return True
        except Exception as exc:
            self._connected = False
            self._client = None
            self._last_error = str(exc)
            logger.warning("Kafka connection failed: %s", exc)
            return False

    def send_event(self, event: dict) -> bool:
        """Publish a telemetry event as JSON, keyed by container_id."""
        if not self.connected and not self.connect():
            return False

        container_id = event.get("container_id")
        if not container_id:
            self._last_error = "Event missing container_id"
            logger.warning(self._last_error)
            return False

        try:
            future = self._client.send(self._topic, key=container_id, value=event)
            future.add_callback(
                lambda metadata, cid=container_id: self._on_send_success(metadata, cid)
            )
            future.add_errback(
                lambda exc, cid=container_id: self._on_send_error(exc, cid)
            )
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning(
                "Kafka publish failed: container_id=%s error=%s",
                container_id,
                exc,
            )
            return False

    def _on_send_success(self, record_metadata: Any, container_id: str) -> None:
        """Log broker acknowledgement metadata after a successful publish."""
        logger.info(
            "Kafka publish succeeded: topic=%s partition=%s offset=%s container_id=%s",
            record_metadata.topic,
            record_metadata.partition,
            record_metadata.offset,
            container_id,
        )

    def _on_send_error(self, exc: Exception, container_id: str | None = None) -> None:
        self._last_error = str(exc)
        if container_id:
            logger.warning(
                "Kafka publish failed: container_id=%s error=%s",
                container_id,
                exc,
            )
        else:
            logger.warning("Kafka send error: %s", exc)

    def flush(self, timeout: float | None = None) -> None:
        """Block until outstanding messages are delivered (or timeout)."""
        if self._client is None:
            return

        try:
            self._client.flush(timeout=timeout)
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Kafka flush failed: %s", exc)

    def close(self) -> None:
        """Flush pending messages and close the producer."""
        if self._client is None:
            return

        try:
            self._client.flush()
            self._client.close()
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Kafka close failed: %s", exc)
        finally:
            self._client = None
            self._connected = False
