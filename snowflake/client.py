"""
Reusable Snowflake client for AtmoSync telemetry ingestion.

All SQL for RAW table management and inserts lives in this module so Kafka
consumers stay free of warehouse-specific statements.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import snowflake.connector
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

RAW_TABLE_NAME = "RAW_SENSOR_EVENTS"

REQUIRED_ENV_VARS: tuple[str, ...] = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
    "SNOWFLAKE_ROLE",
)

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {RAW_TABLE_NAME} (
    container_id STRING,
    shipment_id STRING,
    commodity_id STRING,
    commodity_name STRING,
    event_timestamp TIMESTAMP_NTZ,
    latitude FLOAT,
    longitude FLOAT,
    temperature FLOAT,
    humidity FLOAT,
    vibration FLOAT,
    battery_level FLOAT,
    transport_status STRING,
    anomaly_type STRING,
    health_score FLOAT,
    spoilage_percentage FLOAT,
    remaining_shelf_life_days FLOAT,
    spoilage_risk_level STRING,
    ingested_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
"""

INSERT_EVENT_SQL = f"""
INSERT INTO {RAW_TABLE_NAME} (
    container_id,
    shipment_id,
    commodity_id,
    commodity_name,
    event_timestamp,
    latitude,
    longitude,
    temperature,
    humidity,
    vibration,
    battery_level,
    transport_status,
    anomaly_type,
    health_score,
    spoilage_percentage,
    remaining_shelf_life_days,
    spoilage_risk_level
) VALUES (
    %(container_id)s,
    %(shipment_id)s,
    %(commodity_id)s,
    %(commodity_name)s,
    %(event_timestamp)s,
    %(latitude)s,
    %(longitude)s,
    %(temperature)s,
    %(humidity)s,
    %(vibration)s,
    %(battery_level)s,
    %(transport_status)s,
    %(anomaly_type)s,
    %(health_score)s,
    %(spoilage_percentage)s,
    %(remaining_shelf_life_days)s,
    %(spoilage_risk_level)s
)
"""


def _load_snowflake_config() -> dict[str, str]:
    """Load Snowflake connection settings from environment variables."""
    config: dict[str, str] = {}
    for env_var in REQUIRED_ENV_VARS:
        value = os.getenv(env_var, "").strip()
        if value:
            config[env_var.removeprefix("SNOWFLAKE_").lower()] = value
    return config


def _event_to_row(event: dict[str, Any]) -> dict[str, Any]:
    """Map a validated telemetry event dict to RAW table column names."""
    return {
        "container_id": event["container_id"],
        "shipment_id": event["shipment_id"],
        "commodity_id": event["commodity_id"],
        "commodity_name": event["commodity_name"],
        "event_timestamp": event["timestamp"],
        "latitude": event["latitude"],
        "longitude": event["longitude"],
        "temperature": event["temperature"],
        "humidity": event["humidity"],
        "vibration": event["vibration"],
        "battery_level": event["battery_level"],
        "transport_status": event["transport_status"],
        "anomaly_type": event["anomaly_type"],
        "health_score": event["health_score"],
        "spoilage_percentage": event["spoilage_percentage"],
        "remaining_shelf_life_days": event["remaining_shelf_life_days"],
        "spoilage_risk_level": event["spoilage_risk_level"],
    }


class SnowflakeClient:
    """Manage Snowflake connections and RAW telemetry inserts."""

    def __init__(self, config: dict[str, str] | None = None) -> None:
        self._config = dict(config or _load_snowflake_config())
        self._connection: Any | None = None
        self._last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self._connection is not None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def connect(self) -> bool:
        """Open a Snowflake connection using environment-based credentials."""
        if self._connection is not None:
            return True

        missing = [
            env_var
            for env_var in REQUIRED_ENV_VARS
            if not os.getenv(env_var, "").strip()
        ]
        if missing and not self._config:
            self._last_error = f"Missing required environment variables: {', '.join(missing)}"
            logger.warning("Snowflake connection failed: %s", self._last_error)
            return False

        connect_kwargs = {
            "account": self._config.get("account") or os.getenv("SNOWFLAKE_ACCOUNT", "").strip(),
            "user": self._config.get("user") or os.getenv("SNOWFLAKE_USER", "").strip(),
            "password": self._config.get("password") or os.getenv("SNOWFLAKE_PASSWORD", "").strip(),
            "warehouse": self._config.get("warehouse") or os.getenv("SNOWFLAKE_WAREHOUSE", "").strip(),
            "database": self._config.get("database") or os.getenv("SNOWFLAKE_DATABASE", "").strip(),
            "schema": self._config.get("schema") or os.getenv("SNOWFLAKE_SCHEMA", "").strip(),
            "role": self._config.get("role") or os.getenv("SNOWFLAKE_ROLE", "").strip(),
        }

        missing_kwargs = [key for key, value in connect_kwargs.items() if not value]
        if missing_kwargs:
            self._last_error = f"Missing Snowflake configuration values: {', '.join(missing_kwargs)}"
            logger.warning("Snowflake connection failed: %s", self._last_error)
            return False

        try:
            self._connection = snowflake.connector.connect(**connect_kwargs)
            self._last_error = None
            logger.info("✓ Connected to Snowflake")
            return True
        except Exception as exc:
            self._connection = None
            self._last_error = str(exc)
            logger.warning("Snowflake connection failed: %s", exc)
            return False

    def ensure_table_exists(self) -> bool:
        """Create RAW_SENSOR_EVENTS when it is not already present."""
        if self._connection is None and not self.connect():
            return False

        try:
            cursor = self._connection.cursor()
            try:
                cursor.execute(CREATE_TABLE_SQL)
            finally:
                cursor.close()

            self._last_error = None
            logger.info("✓ RAW table verified")
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("RAW table verification failed: %s", exc)
            return False

    def insert_event(self, event: dict[str, Any]) -> bool:
        """Insert one validated telemetry event into RAW_SENSOR_EVENTS."""
        if self._connection is None and not self.connect():
            logger.warning("✓ Insert failed: Snowflake is not connected")
            return False

        try:
            cursor = self._connection.cursor()
            try:
                cursor.execute(INSERT_EVENT_SQL, _event_to_row(event))
            finally:
                cursor.close()

            self._last_error = None
            logger.info(
                "✓ Event inserted: container_id=%s shipment_id=%s",
                event.get("container_id"),
                event.get("shipment_id"),
            )
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning(
                "✓ Insert failed: container_id=%s error=%s",
                event.get("container_id"),
                exc,
            )
            return False

    def close(self) -> None:
        """Close the Snowflake connection."""
        if self._connection is None:
            return

        try:
            self._connection.close()
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Snowflake close failed: %s", exc)
        finally:
            self._connection = None
