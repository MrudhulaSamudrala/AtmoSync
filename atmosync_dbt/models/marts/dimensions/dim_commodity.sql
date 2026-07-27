with commodities as (

    select distinct
        commodity_id,
        commodity_name
    from {{ ref('stg_sensor_events') }}
    where commodity_id is not null
      and commodity_name is not null

)

select * from commodities
