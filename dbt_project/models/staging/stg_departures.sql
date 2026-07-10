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
    -- `mode` is coarse (all rail-based lines are "train"); `product` is the
    -- granular type (tram, subway, suburban, bus...). Pull it from the raw JSON.
    raw->'line'->>'product' as line_product,
    direction,
    -- a "line variant" = the line together with where it's heading. Delays can
    -- differ per direction, so this is often the more useful unit than the line.
    line_name || ' → ' || coalesce(direction, '?') as line_dir,
    planned_when,
    actual_when,
    -- delay comes back in seconds; expose minutes for convenience
    delay_seconds,
    round(delay_seconds / 60.0, 1) as delay_minutes,
    platform,
    -- daypart classification (based on scheduled time). Rush only applies on
    -- weekdays; weekends are their own bucket. Tweak the hour ranges here.
    case
        when isodow(planned_when) in (6, 7)          then 'weekend'
        when hour(planned_when) between 7 and 9       then 'morning rush'
        when hour(planned_when) between 16 and 18      then 'evening rush'
        else 'off-peak'
    end as daypart,
    -- "settled" = we observed this departure at or after its scheduled time,
    -- so the delay had a chance to become real (not an early optimistic
    -- prediction). loaded_at and planned_when are both stored in local time.
    (loaded_at >= planned_when) as is_settled
from source
-- natural key of a departure = the trip stopping at this station at this time.
-- keep the most recently loaded observation for each.
qualify row_number() over (
    partition by trip_id, station_id, planned_when
    order by loaded_at desc
) = 1
