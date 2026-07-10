-- Average delay per STATION, line and hour of day.
-- Grain = (station, line, product, planned_hour). Station is part of the grain
-- because a delay is always measured at a specific stop - mixing stations would
-- blend unrelated contexts for lines that serve more than one.
with departures as (
    select * from {{ ref('stg_departures') }}
)

select
    station_id,
    station_name,
    line_name,
    line_product,
    date_trunc('hour', planned_when) as planned_hour,
    count(*)                         as num_departures,
    avg(delay_minutes)               as avg_delay_minutes,
    max(delay_minutes)               as max_delay_minutes,
    sum(case when delay_minutes > 5 then 1 else 0 end) as num_late_over_5min
from departures
where planned_when is not null
group by 1, 2, 3, 4, 5
order by station_name, planned_hour, line_name
