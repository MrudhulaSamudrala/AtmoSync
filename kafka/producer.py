"""
Kafka producer module for AtmoSync (placeholder).

Future responsibility:
- Instantiate a Kafka producer using settings from config.kafka_config.
- Accept JSON sensor events from producer/simulator.py (or a thin adapter).
- Publish events to KAFKA_TOPIC with container_id as the message key for partition affinity.
- Handle serialization, retries, and graceful shutdown without blocking the simulator loop.

Implementation will be added in a later step; no Kafka client logic exists yet.
"""
