-- Clean, typed one-row-per-departure model built on the raw table.
with source as (
    select * from {{ source('raw', 'departures') }}
)

select
    loaded_at,
    api,
    station_id,
    station_name,
    trip_id,
    line_name,
    line_mode,
    direction,
    planned_when,
    actual_when,
    -- delay comes back in seconds; expose minutes for convenience
    delay_seconds,
    round(delay_seconds / 60.0, 1) as delay_minutes,
    platform
from source
where trip_id is not null
