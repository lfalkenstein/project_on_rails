"""Streamlit dashboard for transit delay metrics.

Reads the DuckDB warehouse in READ-ONLY mode, so it can run alongside the
scheduled ingest without grabbing the write lock. Plots metrics built by the
dbt model `main.fct_delays_by_line`.

Run it with:
    .\.venv\Scripts\streamlit.exe run dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent / "data" / "warehouse.duckdb"

# Fixed display order for the daypart buckets defined in stg_departures.
DAYPART_ORDER = ["morning rush", "off-peak", "evening rush", "weekend"]

# Shared chart styling (kept tiny on purpose - no custom CSS / themes).
CHART_HEIGHT = 280
COLOR_ACCENT = "#4d8bff"   # neutral series (matches the app accent)
COLOR_LATE = "#ff6b6b"     # delay > 0 (behind schedule)
COLOR_EARLY = "#37c978"    # delay <= 0 (on time / early)

# Colour a delay value red when late, green when on time/early.
_delay_color = alt.condition(
    "datum.avg_delay_minutes > 0", alt.value(COLOR_LATE), alt.value(COLOR_EARLY)
)

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
                line_dir,
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


@st.cache_data(ttl=60)
def load_shown_freshness() -> pd.Timestamp | None:
    """Latest departure time represented in the marts the dashboard renders.

    This reflects what the CHARTS actually show (built by dbt), not when the raw
    ingest last ran - so it won't claim a freshness the visualised data doesn't
    have. The marts only include *settled* departures, so this figure naturally
    trails "now" by the settle delay, which is honest rather than a bug.
    """
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        row = con.sql("select max(bucket_5min) from main.fct_departures_5min").fetchone()
    return pd.Timestamp(row[0]) if row and row[0] is not None else None


@st.cache_data(ttl=60)
def load_5min() -> pd.DataFrame:
    """Load the 5-minute time-series mart (read-only, cached 60s)."""
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.sql(
            """
            select
                bucket_5min,
                station_name,
                line_name,
                line_dir,
                line_product,
                daypart,
                num_departures,
                num_settled,
                avg_delay_minutes
            from main.fct_departures_5min
            order by bucket_5min
            """
        ).df()


st.title("🚆 project_on_rails")
st.markdown(
    "#### Public-transport punctuality — delays by line & direction"
)

# ---- Freshness watermark ---------------------------------------------------
# Show how current the DATA IN THE CHARTS is (latest departure built into the
# marts), not when raw ingest last ran - the two differ because dbt is rebuilt
# manually. Data is cached for 60s; it also refreshes via Streamlit's built-in
# "Clear cache" / "Rerun" menu (top-right).
try:
    _fresh = load_shown_freshness()
except duckdb.IOException:
    _fresh = None
_rendered = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
if _fresh is not None:
    st.caption(
        f"🟢 Data shown up to **{_fresh:%Y-%m-%d %H:%M}** (latest settled departure) "
        f"· page rendered {_rendered}"
    )
else:
    st.caption(f"Page rendered {_rendered} · data freshness unavailable")

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

lines = sorted(sdf.loc[sdf["line_product"].isin(sel_products), "line_dir"].dropna().unique())
sel_lines = st.sidebar.multiselect("Line → destination", lines, default=lines)

dayparts = [d for d in DAYPART_ORDER if d in sdf["daypart"].unique()]
sel_dayparts = st.sidebar.multiselect("Daypart", dayparts, default=dayparts)

fdf = sdf[
    sdf["line_product"].isin(sel_products)
    & sdf["line_dir"].isin(sel_lines)
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

on_time_pct = 100 - late_pct
c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Departures", f"{total_departures:,}",
    help="Settled departures matching the current filters.",
    border=True,
)
c2.metric(
    "Avg delay", f"{avg_delay:.1f} min",
    help="Departure-weighted average delay. Negative = early.",
    border=True,
)
c3.metric(
    "Late > 5 min", f"{late:,}",
    delta=f"{late_pct:.0f}% of departures", delta_color="inverse",
    help="Departures more than 5 minutes late.",
    border=True,
)
c4.metric(
    "On time", f"{on_time_pct:.0f}%",
    help="Share of departures within 5 minutes of schedule.",
    border=True,
)

st.divider()

# ---- Charts ----------------------------------------------------------------
def _wavg(g: pd.DataFrame) -> float:
    """Departure-weighted average delay for a group."""
    return (g["avg_delay_minutes"] * g["num_departures"]).sum() / g["num_departures"].sum()

st.subheader("Average delay by line → destination")
# Horizontal bars so the long "line → destination" labels stay readable, and
# the bar length maps to delay (red = late, green = on time / early).
by_line = (
    fdf.groupby("line_dir").apply(_wavg, include_groups=False)
    .rename("avg_delay_minutes").reset_index()
)
line_chart = (
    alt.Chart(by_line)
    .mark_bar(cornerRadiusEnd=3)
    .encode(
        x=alt.X("avg_delay_minutes:Q", title="avg delay (min)"),
        y=alt.Y("line_dir:N", sort="-x", title=None),
        color=_delay_color,
        tooltip=[
            alt.Tooltip("line_dir:N", title="Line"),
            alt.Tooltip("avg_delay_minutes:Q", title="Avg delay (min)", format=".1f"),
        ],
    )
    .properties(height=max(140, 30 * len(by_line)))
)
st.altair_chart(line_chart, use_container_width=True)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("By daypart")
    present_dayparts = [d for d in DAYPART_ORDER if d in fdf["daypart"].unique()]
    by_daypart = (
        fdf.groupby("daypart").apply(_wavg, include_groups=False)
        .rename("avg_delay_minutes").reset_index()
    )
    daypart_chart = (
        alt.Chart(by_daypart)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("daypart:N", sort=present_dayparts, title=None),
            y=alt.Y("avg_delay_minutes:Q", title="avg delay (min)"),
            color=_delay_color,
            tooltip=[
                alt.Tooltip("daypart:N", title="Daypart"),
                alt.Tooltip("avg_delay_minutes:Q", title="Avg delay (min)", format=".1f"),
            ],
        )
        .properties(height=CHART_HEIGHT)
    )
    st.altair_chart(daypart_chart, use_container_width=True)

with col_b:
    st.subheader("By hour of day")
    by_hour = (
        fdf.groupby("planned_hour").apply(_wavg, include_groups=False)
        .rename("avg_delay_minutes").reset_index()
    )
    zero_rule = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        color="#5b6472", strokeDash=[4, 4]
    ).encode(y="y:Q")
    hour_line = (
        alt.Chart(by_hour)
        .mark_line(point=True, color=COLOR_ACCENT)
        .encode(
            x=alt.X("planned_hour:T", title=None),
            y=alt.Y("avg_delay_minutes:Q", title="avg delay (min)"),
            tooltip=[
                alt.Tooltip("planned_hour:T", title="Hour", format="%Y-%m-%d %H:%M"),
                alt.Tooltip("avg_delay_minutes:Q", title="Avg delay (min)", format=".1f"),
            ],
        )
        .properties(height=CHART_HEIGHT)
    )
    st.altair_chart(zero_rule + hour_line, use_container_width=True)

# ---- Fine-grained time series (5-min buckets) -----------------------------
st.header("Fine-grained trends (5-min buckets)")

# At 5-min resolution the full history gets crowded, so default to a recent
# window. Anchored to the LATEST bucket present (not wall-clock now), because
# the marts only hold settled departures and therefore trail the present - an
# "up to now" window would otherwise cut off the most recent data.
WINDOW_OPTIONS = {
    "Last 1 hour": 1,
    "Last 3 hours": 3,
    "Last 6 hours": 6,
    "Last 12 hours": 12,
    "Last 24 hours": 24,
    "All": None,
}
window_label = st.selectbox(
    "Time window", list(WINDOW_OPTIONS), index=2, key="fine_window"  # default: last 6 hours
)
window_hours = WINDOW_OPTIONS[window_label]

try:
    fine = load_5min()
except duckdb.IOException:
    fine = pd.DataFrame()

# reuse the same filters as above
fine = fine[
    fine["station_name"].isin(sel_stations)
    & fine["line_product"].isin(sel_products)
    & fine["line_dir"].isin(sel_lines)
    & fine["daypart"].isin(sel_dayparts)
]

if fine.empty:
    st.info("No fine-grained data for the current filters yet.")
else:
    fine = fine.copy()
    fine["bucket_5min"] = pd.to_datetime(fine["bucket_5min"])

    # Trim to the selected rolling window, anchored to the latest bucket we have.
    if window_hours is not None:
        latest = fine["bucket_5min"].max()
        cutoff = latest - pd.Timedelta(hours=window_hours)
        fine = fine[fine["bucket_5min"] >= cutoff]
        st.caption(
            f"Showing {cutoff:%Y-%m-%d %H:%M} – {latest:%H:%M} "
            f"({window_label.lower()} of available data)"
        )

    # ---- Volume: one stacked bar per 5-min bucket, split by line ----
    # Stacked by line_dir so each bucket shows its per-line composition, and the
    # Altair tooltip surfaces the exact line + count for the hovered segment.
    st.subheader("Departure volume (5-min buckets)")
    vol_by_line = (
        fine.groupby(["bucket_5min", "line_dir"], as_index=False)["num_departures"].sum()
    )
    vol_chart = (
        alt.Chart(vol_by_line)
        .mark_bar()
        .encode(
            x=alt.X("bucket_5min:T", title="5-min bucket"),
            y=alt.Y("sum(num_departures):Q", title="departures", stack=True),
            color=alt.Color("line_dir:N", title="Line → destination"),
            tooltip=[
                alt.Tooltip("bucket_5min:T", title="Bucket", format="%Y-%m-%d %H:%M"),
                alt.Tooltip("line_dir:N", title="Line"),
                alt.Tooltip("num_departures:Q", title="Departures"),
            ],
        )
    )
    st.altair_chart(vol_chart, use_container_width=True)

    # ---- Delay trend: noisy per-bucket delay smoothed by a rolling average ----
    # Per-5-min delay is very noisy (few departures per bucket), so we smooth it
    # with a moving average. The slider sets how many hours the window covers.
    st.subheader("Delay trend (settled only, rolling average)")
    delay_hours = st.slider(
        "Smoothing window (hours)",
        min_value=0.5, max_value=48.0, value=2.0, step=0.5, key="delay_win",
    )

    def _wavg_delay(g: pd.DataFrame) -> float:
        w = g["num_settled"].sum()
        if not w:
            return float("nan")
        return (g["avg_delay_minutes"].fillna(0) * g["num_settled"]).sum() / w

    delay5 = (
        fine.groupby("bucket_5min").apply(_wavg_delay, include_groups=False).sort_index()
        .asfreq("5min")  # NaN where no settled departures
    )
    win = max(1, int(delay_hours * 12))  # 12 buckets per hour
    delay_out = pd.DataFrame(
        {
            "delay per 5-min (raw)": delay5,
            f"rolling avg ({delay_hours:g}h)": delay5.rolling(win, min_periods=1).mean(),
        }
    )
    st.line_chart(delay_out)

# ---- Raw table -------------------------------------------------------------
with st.expander("Show underlying data"):
    st.dataframe(fdf, use_container_width=True)
