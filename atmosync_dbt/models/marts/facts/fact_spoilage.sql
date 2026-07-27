select
    container_id,
    shipment_id,
    commodity_id,
    commodity_name,
    spoilage_percentage,
    remaining_shelf_life_days,
    spoilage_risk_level,
    health_score,
    event_timestamp
from {{ ref('stg_sensor_events') }}
