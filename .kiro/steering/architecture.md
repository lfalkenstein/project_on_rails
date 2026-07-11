# project_on_rails — architecture & conventions

Living guide to this project's decisions and patterns. Focused on the durable
*why*, not volatile specifics (column names, intervals, values), so it ages
slowly. If a change contradicts something here, update this file.

## What it is
Personal data project: ingest public-transport data (DB/BVG APIs via
transport.rest) in near real time → DuckDB → dbt → Streamlit dashboard. Goal is
to measure punctuality/delays per line and direction.

## Data flow (the backbone)
`APIs → ingestion (Python) → raw (DuckDB) → dbt (staging → marts) → dashboard`

- **Ingestion** (`ingest/`): thin HTTP client over transport.rest, YAML-driven config.
- **raw** (`raw.departures`): append-only layer, the crude history.
- **dbt** (`dbt_project/`): `stg_departures` (one clean, typed row per departure) and
  aggregated marts (`fct_delays_by_line`, `fct_departures_5min`).
- **dashboard** (`dashboard.py`): Streamlit on top of the marts.

## Key decisions and their rationale

### Ingestion
- **Config-driven**: what to collect lives in `ingest_config.yml` (stations, API,
  window). *When* it runs is the scheduler's job, not the code's.
- **raw is append-only with content-hash dedup**: each observation carries a hash of
  its meaningful fields; only new or changed observations are inserted. This captures
  how a delay evolves without duplicating noise. The final per-departure dedup is done
  by dbt.
- **Retry with backoff for transient errors** (429/5xx, timeouts): upstream APIs fail
  intermittently; permanent errors (e.g. 404) are not retried.
- **Per-station isolation**: if one station fails (after retries), it doesn't abort the
  collection of the others; the failure is counted and the process exits non-zero.
- **On-disk station-id cache**: resolving name→id is stable, so it's cached to avoid
  repeating the `/locations` search on every run (fewer calls, smaller failure surface).
  `--refresh-stations` forces re-resolution.

### Modeling (dbt)
- **staging types and deduplicates**: `stg_departures` keeps one row per departure
  (latest observation per `trip_id + station_id + planned_when`).
- **`is_settled` means "the expected time has now passed" measured against a freshness
  watermark** (`max(loaded_at)`), not "we observed the departure at/after its scheduled
  time". Reason: vehicles drop out of the feed right before they leave, so the last
  observation is almost always *before* the scheduled time. The watermark-based
  definition avoids discarding most departures (and prevents whole directions from
  disappearing from the dashboard).
- **The useful grain is usually line + direction** (`line_dir`), not just the line:
  delays differ per direction.

### Dashboard
- **Connects to DuckDB in READ-ONLY mode**: so it coexists with ingestion without
  fighting for the write lock (DuckDB is single-writer).
- **Loads the marts and caches in memory** (`@st.cache_data`, short ttl); filtering is
  done in pandas on the cached dataframe. Valid pattern while the data is small and
  there's a single user. If the mart grows or concurrency appears, the next step is to
  push filters/aggregations into SQL and cache per-slice (not done: YAGNI for now).
- **The freshness watermark reflects the data shown** (latest bucket in the mart), not
  when raw ingestion last ran, so it doesn't promise a freshness the charts don't have.

## Scheduling
- On Windows it runs as a Scheduled Task. The definition lives in
  `scripts/ingest_task.xml` (single source of truth; edit the XML and re-register, not
  the GUI).
- The task runs **ingestion only** (`run_ingest.ps1`); dbt is **not** in that loop and is
  rebuilt separately (`dbt run` or `run_pipeline.ps1`).
- Lesson learned: a time-only trigger doesn't survive a reboot-without-login well; hence
  it also carries a logon trigger.

## How to run (quick reference)
Always run dbt from the repo root (the profile resolves the path relatively):
```
.venv\Scripts\python -m ingest
.venv\Scripts\dbt run --project-dir dbt_project --profiles-dir dbt_project
.venv\Scripts\streamlit run dashboard.py --server.headless true
```

## Working principles
- **YAGNI**: don't add complexity (query-on-demand, partitioning, multi-user) until the
  data or usage demands it. The refactor to SQL-pushed queries is mechanical and cheap
  to do later, so waiting costs nothing.
- **Document the durable why, not the volatile what**: applies to this file, the README
  and the scheduling. Avoids drift between docs and reality.
