-- Clean, typed one-row-per-departure model built on the raw table.
--
-- The raw table is append-only, so the same departure can appear many times
-- (one row per collection run, sometimes with an updated delay). We keep only
-- the LATEST observation per departure using its natural key.
with source as (
    select * from {{ source('raw', 'departures') }}
    where trip_id is not null
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
-- natural key of a departure = the trip stopping at this station at this time.
-- keep the most recently loaded observation for each.
qualify row_number() over (
    partition by trip_id, station_id, planned_when
    order by loaded_at desc
) = 1
