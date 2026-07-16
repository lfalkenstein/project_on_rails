-- Classifies each line→destination served at a stop as regular revenue service,
-- a rare/transient variant, or a non-revenue depot (Betriebshof) run - so the
-- punctuality mart and the dashboard can filter out noise.
--
-- Grain = (station, line, direction).
--
-- Primary signal is share-based and self-normalizing: within a stop, each
-- destination's share of its LINE's departures. A real destination dominates
-- (e.g. U5 → Kaulsdorf-Nord), while once-a-day short-turns and depot runs sit
-- far below (U5 → Frankfurter Allee with a single sighting). Share is only
-- trusted once the line has enough departures at the stop (MIN_LINE_SAMPLE);
-- below that we mark 'low_confidence' instead of guessing.
--
-- Thresholds are inlined on purpose (small learning project); tweak here.
--   share cutoff     = 0.10   (a real destination is >=10% of its line at the stop)
--   MIN_LINE_SAMPLE  = 20     (departures of a line at a stop before share is trusted)

with departures as (
    select * from {{ ref('stg_departures') }}
    where planned_when is not null
),

by_line_dir as (
    select
        station_id,
        station_name,
        line_name,
        line_product,
        direction,
        line_dir,
        count(*)                                    as num_departures,
        count(distinct cast(planned_when as date))  as days_observed
    from departures
    group by 1, 2, 3, 4, 5, 6
),

with_share as (
    select
        *,
        sum(num_departures) over (partition by station_id, line_name) as line_stop_total,
        num_departures::double
            / sum(num_departures) over (partition by station_id, line_name) as dest_share
    from by_line_dir
),

classified as (
    select
        *,
        (direction ilike '%Betriebshof%') as is_deadhead,
        case
            when direction ilike '%Betriebshof%' then 'deadhead'
            when line_stop_total < 20            then 'low_confidence'
            when dest_share >= 0.10              then 'regular'
            else 'transient'
        end as service_class
    from with_share
)

select
    station_id,
    station_name,
    line_name,
    line_product,
    direction,
    line_dir,
    num_departures,
    days_observed,
    line_stop_total,
    round(dest_share, 4)                  as dest_share,
    is_deadhead,
    service_class,
    (service_class = 'regular')           as is_regular_service,
    -- confidence 0-1: grows with the line's sample at this stop, capped at 1.
    -- (days_observed is exposed too so the dashboard can caveat short history.)
    round(least(1.0, line_stop_total / 20.0), 2) as confidence
from classified
order by station_name, line_name, num_departures desc
