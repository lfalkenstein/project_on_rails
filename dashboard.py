"""Streamlit dashboard for transit delay metrics.

Reads the DuckDB warehouse in READ-ONLY mode, so it can run alongside the
scheduled ingest without grabbing the write lock. Plots metrics built by the
dbt model `main.fct_delays_by_line`.

Run it with:
    .\.venv\Scripts\streamlit.exe run dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent / "data" / "warehouse.duckdb"

# Fixed display order for the daypart buckets defined in stg_departures.
DAYPART_ORDER = ["morning rush", "off-peak", "evening rush", "weekend"]

st.set_page_config(page_title="project_on_rails — delays", layout="wide")


@st.cache_data(ttl=60)
def load_fct() -> pd.DataFrame:
    """Load the delays mart. Cached for 60s; read-only so it won't block ingest."""
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.sql(
            """
            select
                station_name,
                line_name,
                line_product,
                planned_hour,
                daypart,
                num_departures,
                avg_delay_minutes,
                max_delay_minutes,
                num_late_over_5min
            from main.fct_delays_by_line
            order by station_name, planned_hour, line_name
            """
        ).df()


st.title("🚆 project_on_rails — delays by line")

if not DB_PATH.exists():
    st.error(f"No warehouse found at {DB_PATH}. Run an ingest + `dbt run` first.")
    st.stop()

try:
    df = load_fct()
except duckdb.IOException as exc:
    st.warning(
        "Could not open the warehouse (it may be mid-write by the ingest, "
        "or open read-write in DBeaver). Try again in a moment.\n\n"
        f"{exc}"
    )
    if st.button("Retry"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

if df.empty:
    st.info("The mart is empty. Collect some data and run `dbt run`.")
    st.stop()

# ---- Sidebar filters -------------------------------------------------------
st.sidebar.header("Filters")
stations = sorted(df["station_name"].dropna().unique())
sel_stations = st.sidebar.multiselect("Station", stations, default=stations)

sdf = df[df["station_name"].isin(sel_stations)]

products = sorted(sdf["line_product"].dropna().unique())
sel_products = st.sidebar.multiselect("Type", products, default=products)

lines = sorted(sdf.loc[sdf["line_product"].isin(sel_products), "line_name"].dropna().unique())
sel_lines = st.sidebar.multiselect("Line", lines, default=lines)

dayparts = [d for d in DAYPART_ORDER if d in sdf["daypart"].unique()]
sel_dayparts = st.sidebar.multiselect("Daypart", dayparts, default=dayparts)

fdf = sdf[
    sdf["line_product"].isin(sel_products)
    & sdf["line_name"].isin(sel_lines)
    & sdf["daypart"].isin(sel_dayparts)
]

if fdf.empty:
    st.info("No rows match the current filters.")
    st.stop()

# ---- KPIs ------------------------------------------------------------------
total_departures = int(fdf["num_departures"].sum())
# weighted average delay (by number of departures)
avg_delay = (fdf["avg_delay_minutes"] * fdf["num_departures"]).sum() / total_departures
late = int(fdf["num_late_over_5min"].sum())
late_pct = 100 * late / total_departures if total_departures else 0

c1, c2, c3 = st.columns(3)
c1.metric("Departures", f"{total_departures:,}")
c2.metric("Avg delay (min)", f"{avg_delay:.1f}")
c3.metric("Late > 5 min", f"{late} ({late_pct:.0f}%)")

# ---- Charts ----------------------------------------------------------------
st.subheader("Average delay by line")
by_line = (
    fdf.groupby("line_name")
    .apply(lambda g: (g["avg_delay_minutes"] * g["num_departures"]).sum() / g["num_departures"].sum())
    .sort_values(ascending=False)
    .rename("avg_delay_minutes")
)
st.bar_chart(by_line)

st.subheader("Average delay by daypart")
by_daypart = (
    fdf.groupby("daypart")
    .apply(lambda g: (g["avg_delay_minutes"] * g["num_departures"]).sum() / g["num_departures"].sum())
    .rename("avg_delay_minutes")
    .reindex([d for d in DAYPART_ORDER if d in fdf["daypart"].unique()])
)
st.bar_chart(by_daypart)

st.subheader("Average delay over time (by hour)")
by_hour = (
    fdf.groupby("planned_hour")
    .apply(lambda g: (g["avg_delay_minutes"] * g["num_departures"]).sum() / g["num_departures"].sum())
    .rename("avg_delay_minutes")
)
st.line_chart(by_hour)

st.subheader("Departure volume by hour")
vol = fdf.groupby("planned_hour")["num_departures"].sum()
st.bar_chart(vol)

# ---- Raw table -------------------------------------------------------------
with st.expander("Show underlying data"):
    st.dataframe(fdf, use_container_width=True)
