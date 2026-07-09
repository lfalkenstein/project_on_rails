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

## Run the pipeline
```powershell
# 1. Ingest: fetch departures into DuckDB
python -m ingest --station "Berlin Hbf" --duration 60

# 2. Transform: build staging + marts models
dbt run --project-dir dbt_project --profiles-dir dbt_project

# 3. Explore
python -c "import duckdb; print(duckdb.connect('data/warehouse.duckdb').sql('select * from main.fct_delays_by_line limit 10'))"
```

Switch APIs by setting `TRANSPORT_API=bvg` in `.env`.

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
