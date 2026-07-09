# project_on_rails

A personal learning project: pull live transit data from the Deutsche Bahn / BVG
APIs with Python, land it in DuckDB, and transform it with dbt.

## Stack
- **Python** ingestion (`httpx`) → `ingest/`
- **DuckDB** as the warehouse → `data/warehouse.duckdb`
- **dbt** (`dbt-duckdb`) for transforms → `dbt_project/`
- Free community APIs (no key needed): https://v6.db.transport.rest / https://v6.bvg.transport.rest

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

## What gets collected (`ingest_config.yml`)
This single file controls **which stations** and **which API**:
```yaml
api: bvg          # "db" (Deutsche Bahn) or "bvg" (Berlin)
duration: 60      # look-ahead window in minutes
stations:
  - search: "Alexanderplatz"
  - search: "Berlin Hauptbahnhof"
```
Preview how a name resolves before adding it:
```powershell
python -m ingest --find "Ostkreuz"
```

## Run the pipeline
```powershell
# Full cycle (ingest all configured stations, then build dbt models):
powershell -ExecutionPolicy Bypass -File scripts\run_pipeline.ps1

# Or step by step:
python -m ingest                 # collect every station in ingest_config.yml
python -m ingest --api db        # override the API for one run
python -m ingest --station "Berlin Hbf"   # one-off single station
dbt run --project-dir dbt_project --profiles-dir dbt_project

# Explore
python query.py "select * from main.fct_delays_by_line limit 10"
```

> Note: DuckDB is single-writer across processes. Disconnect any DBeaver /
> notebook connection to `data/warehouse.duckdb` before running an ingest.

## Scheduling (WHEN it runs)
The pipeline only runs when triggered. To collect data continuously, register
a Windows Scheduled Task that calls the wrapper script on a timer.

Example: run every 15 minutes (adjust the path/interval as needed):
```powershell
schtasks /Create /TN "project_on_rails ingest" /SC MINUTE /MO 15 ^
  /TR "powershell -ExecutionPolicy Bypass -File \"%CD%\scripts\run_pipeline.ps1\"" ^
  /F
```
Manage it with:
```powershell
schtasks /Run    /TN "project_on_rails ingest"   # run once now
schtasks /Query  /TN "project_on_rails ingest"   # check status / next run
schtasks /Delete /TN "project_on_rails ingest" /F
```
On macOS/Linux the equivalent is a cron entry calling the same commands.

## Layout
```
ingest/                 Python API client + DuckDB loader
dbt_project/
  models/staging/       1:1 typed views over raw tables
  models/marts/         aggregated tables for analysis
data/warehouse.duckdb   the DuckDB file (git-ignored)
```

## Learning milestones
1. Get one ingest run writing rows to `raw.departures`.
2. `dbt run` builds `stg_departures` and `fct_delays_by_line`.
3. Schedule the ingest (Task Scheduler / cron) to collect a day of data.
4. Add a notebook to plot delays by hour.
