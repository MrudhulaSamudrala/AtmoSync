select
    container_id,
    shipment_id,
    event_timestamp,
    temperature,
    humidity,
    vibration,
    battery_level,
    health_score,
    transport_status,
    anomaly_type,
    latitude,
    longitude
from {{ ref('stg_sensor_events') }}
