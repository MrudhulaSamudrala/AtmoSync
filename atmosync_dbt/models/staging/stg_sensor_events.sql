with source as (

    select * from {{ source('raw', 'raw_sensor_events') }}

),

renamed as (

    select
        trim(container_id)::varchar as container_id,
        trim(shipment_id)::varchar as shipment_id,
        trim(commodity_id)::varchar as commodity_id,
        trim(commodity_name)::varchar as commodity_name,
        event_timestamp::timestamp_ntz as event_timestamp,
        latitude::float as latitude,
        longitude::float as longitude,
        temperature::float as temperature,
        humidity::float as humidity,
        vibration::float as vibration,
        battery_level::float as battery_level,
        trim(transport_status)::varchar as transport_status,
        trim(anomaly_type)::varchar as anomaly_type,
        health_score::float as health_score,
        spoilage_percentage::float as spoilage_percentage,
        remaining_shelf_life_days::float as remaining_shelf_life_days,
        trim(spoilage_risk_level)::varchar as spoilage_risk_level,
        ingested_at::timestamp_ntz as ingested_at

    from source

)

select * from renamed
