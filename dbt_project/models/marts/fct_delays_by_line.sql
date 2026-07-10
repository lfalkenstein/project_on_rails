-- Average delay per line and hour of day. A simple first mart to explore.
with departures as (
    select * from {{ ref('stg_departures') }}
)

select
    line_name,
    line_product,
    date_trunc('hour', planned_when) as planned_hour,
    count(*)                         as num_departures,
    avg(delay_minutes)               as avg_delay_minutes,
    max(delay_minutes)               as max_delay_minutes,
    sum(case when delay_minutes > 5 then 1 else 0 end) as num_late_over_5min
from departures
where planned_when is not null
group by 1, 2, 3
order by planned_hour, line_name
