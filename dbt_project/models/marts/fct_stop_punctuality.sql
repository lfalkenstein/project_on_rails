-- Punctuality ranking per stop.
-- Grain = (station).
--
-- "On time" = delay <= 3 minutes (early counts as on time). This is stricter
-- than the >5-min "late" flag used elsewhere; the ranking gets its own bar.
--
-- The score is a rush-weighted on-time %: we compute on-time % per daypart, then
-- combine dayparts with importance weights so rush-hour reliability matters more
-- than off-peak. Weights: morning/evening rush = 2, off-peak = 1, weekend = 0.5.
--
-- Only REGULAR revenue service counts (see dim_stop_line_service): depot runs
-- and rare/transient short-turns are excluded so the score reflects the everyday
-- service a rider actually experiences. Settled departures only (real delays).

with regular as (
    select d.*
    from {{ ref('stg_departures') }} d
    join {{ ref('dim_stop_line_service') }} s
        on d.station_id = s.station_id
       and d.line_dir   = s.line_dir
    where d.is_settled
      and d.planned_when is not null
      and s.is_regular_service
),

by_daypart as (
    select
        station_id,
        station_name,
        daypart,
        count(*)                                       as n,
        count(*) filter (where delay_minutes <= 3)     as n_ontime,
        100.0 * count(*) filter (where delay_minutes <= 3) / count(*) as ontime_pct
    from regular
    group by 1, 2, 3
),

weighted as (
    select
        *,
        case daypart
            when 'morning rush' then 2.0
            when 'evening rush' then 2.0
            when 'off-peak'     then 1.0
            when 'weekend'      then 0.5
            else 1.0
        end as weight
    from by_daypart
)

select
    station_id,
    station_name,
    sum(n)                                             as num_departures,
    sum(n_ontime)                                      as num_ontime,
    -- plain (unweighted) on-time %, for reference
    round(100.0 * sum(n_ontime) / sum(n), 1)           as ontime_pct,
    -- rush-weighted score (0-100, higher = more punctual) - the ranking metric
    round(sum(ontime_pct * weight) / sum(weight), 1)   as punctuality_score,
    count(distinct daypart)                            as dayparts_covered
from weighted
group by 1, 2
order by punctuality_score desc
