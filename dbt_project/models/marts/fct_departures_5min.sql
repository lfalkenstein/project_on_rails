-- Fine-grained time series: departures bucketed into 5-minute intervals.
-- Meant for volume charts and rolling-window trends in the dashboard.
--
-- Grain = (5-min bucket, station, line, product, daypart).
-- num_departures counts ALL departures (a schedule fact, so future/unsettled
-- ones count too). avg_delay_minutes uses only SETTLED observations, to avoid
-- the optimistic bias of not-yet-departed trips.
with departures as (
    select * from {{ ref('stg_departures') }}
    where planned_when is not null
)

select
    time_bucket(interval '5 minutes', planned_when) as bucket_5min,
    station_id,
    station_name,
    line_name,
    line_product,
    daypart,
    count(*)                                         as num_departures,
    count(*) filter (where is_settled)               as num_settled,
    avg(delay_minutes) filter (where is_settled)     as avg_delay_minutes
from departures
group by 1, 2, 3, 4, 5, 6
order by bucket_5min, station_name, line_name
