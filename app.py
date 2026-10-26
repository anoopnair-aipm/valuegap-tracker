"""ValueGap Tracker — Streamlit dashboard.

    streamlit run app.py

Three steps, matching the MVP scope:
  1. Define a pilot (or use the generic sample).
  2. Import monthly actuals from CSV. Outside sample mode, the pilot and every
     imported month are kept in a local SQLite history (valuegap.db), so you
     define the pilot once and add one month at a time.
  3. View the dashboard: promised vs. realized hours by month, realization rate,
     cost per successful outcome, cumulative net value, the monthly table, and
     the executive summary with its leak check.

Everything runs locally. Claude narration is optional: with ANTHROPIC_API_KEY
set, a button asks for it once and the result is reused until the numbers change.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import streamlit as st

from valuegap.calculations import PAYBACK_LOST, analyze
from valuegap.narrator import facts_from_summary, narrate
from valuegap.report import (
    build_summary,
    fmt_money,
    fmt_money2,
    fmt_pct,
    leak_headline,
    render_html,
    render_text,
)
from valuegap.storage import (
    connect,
    get_actuals,
    get_pilot,
    list_pilots,
    load_actuals_csv,
    load_actuals_text,
    save_history,
    save_pilot,
)
from valuegap.validation import ValidationError, parse_pilot

APP_DIR = Path(__file__).parent
SAMPLE_PILOT = APP_DIR / "data" / "sample_pilot.json"
SAMPLE_CSV = APP_DIR / "data" / "sample_monthly.csv"
DB_PATH = Path(os.environ.get("VALUEGAP_DB", APP_DIR / "valuegap.db"))

# On a shared public host every visitor would see every saved pilot, so there
# each browser session gets its own in-memory history instead. Streamlit
# Community Cloud serves apps from /mount/src/; VALUEGAP_PUBLIC_DEMO forces it.
PUBLIC_DEMO = (
    os.environ.get("VALUEGAP_PUBLIC_DEMO", "").lower() in ("1", "true", "yes")
    or str(APP_DIR).startswith("/mount/src/")
)

NEW_PILOT = "➕ New pilot"
BLANK_PILOT = {
    "name": "",
    "start_month": "2026-01",
    "implementation_cost": 0.0,
    "value_per_hour": 0.0,
    "promised_hours_saved": 0.0,
    "promised_successful_outcomes": 0.0,
    "promised_success_rate": 0.0,
    "promised_ai_cost_budget": 0.0,
}


def show_problems(title: str, err: ValidationError) -> None:
    st.error(title + "\n\n" + "\n".join(f"- {p}" for p in err.problems))


st.set_page_config(page_title="ValueGap Tracker", page_icon="📉", layout="wide")
st.title("📉 ValueGap Tracker")
st.caption(
    "Adoption is not value. Track whether an AI pilot delivered the value it "
    "promised, month by month. Thresholds and value-per-hour are user-entered "
    "starting defaults, not benchmarks."
)

# ---------------------------------------------------------------------------
# Step 1 — define the pilot
# ---------------------------------------------------------------------------
st.header("1. Define the pilot")

use_sample = st.toggle("Use the shipped sample pilot (illustrative only)", value=True)
conn = None

if use_sample:
    sp = json.loads(SAMPLE_PILOT.read_text())
else:
    if PUBLIC_DEMO:
        if "demo_db" not in st.session_state:
            st.session_state.demo_db = connect(":memory:")
        conn = st.session_state.demo_db
        st.caption(
            "Public demo: pilots you enter are kept only in this browser session, "
            "are not visible to anyone else, and are gone when you close the tab. "
            "Don't enter confidential figures."
        )
    else:
        conn = connect(str(DB_PATH))
    choice = st.selectbox("Pilot", [NEW_PILOT] + list_pilots(conn))
    stored = get_pilot(conn, choice) if choice != NEW_PILOT else None
    sp = vars(stored) if stored else BLANK_PILOT

c1, c2, c3 = st.columns(3)
with c1:
    name = st.text_input("Pilot name (generic)", value=sp["name"])
    start_month = st.text_input("Start month (YYYY-MM)", value=sp["start_month"])
    implementation_cost = st.number_input(
        "One-time implementation cost ($)", value=float(sp["implementation_cost"]),
        min_value=0.0, step=1000.0,
    )
with c2:
    value_per_hour = st.number_input(
        "Value per hour saved ($) — your assumption", value=float(sp["value_per_hour"]),
        min_value=0.0, step=5.0,
    )
    promised_hours_saved = st.number_input(
        "Promised hours saved / month", value=float(sp["promised_hours_saved"]),
        min_value=0.0, step=10.0,
    )
    promised_successful_outcomes = st.number_input(
        "Promised successful outcomes / month",
        value=float(sp["promised_successful_outcomes"]), min_value=0.0, step=10.0,
    )
with c3:
    promised_success_rate = st.number_input(
        "Promised success rate (0-1) — the quality Green line",
        value=float(sp["promised_success_rate"]), min_value=0.0, max_value=1.0, step=0.05,
    )
    promised_ai_cost_budget = st.number_input(
        "Promised AI cost budget / month ($)", value=float(sp["promised_ai_cost_budget"]),
        min_value=0.0, step=50.0,
    )

try:
    pilot = parse_pilot(
        {
            "name": name,
            "start_month": start_month,
            "implementation_cost": implementation_cost,
            "value_per_hour": value_per_hour,
            "promised_hours_saved": promised_hours_saved,
            "promised_successful_outcomes": promised_successful_outcomes,
            "promised_success_rate": promised_success_rate,
            "promised_ai_cost_budget": promised_ai_cost_budget,
        }
    )
except ValidationError as e:
    show_problems("Fix the pilot definition to continue:", e)
    st.stop()

st.caption(
    f"Derived cost-per-outcome target: {fmt_money2(pilot.target_cost_per_outcome)} "
    "(= promised AI budget ÷ promised successful outcomes)."
)
if conn is not None and st.button("Save pilot"):
    save_pilot(conn, pilot)
    st.success(f"Saved '{pilot.name}' to the local history.")

# ---------------------------------------------------------------------------
# Step 2 — import monthly actuals
# ---------------------------------------------------------------------------
st.header("2. Import monthly actuals (CSV)")
st.caption(
    "One row per month. Columns: month, hours_saved, successful_outcomes, "
    "total_outcomes, ai_cost, rework_hours, active_users, eligible_users."
)

if use_sample:
    actuals = load_actuals_csv(SAMPLE_CSV)
    st.caption("Using the shipped 6-month sample actuals (not saved to history).")
else:
    uploaded = st.file_uploader("Upload a monthly actuals CSV", type="csv")
    if uploaded is not None:
        try:
            new_rows = load_actuals_text(uploaded.getvalue().decode("utf-8-sig"))
        except (ValidationError, UnicodeDecodeError) as e:
            if isinstance(e, UnicodeDecodeError):
                e = ValidationError(["The file is not UTF-8 text. Save it as CSV (UTF-8)."])
            show_problems("This CSV was not imported:", e)
            st.stop()
        if st.button(f"Import {len(new_rows)} month(s) into '{pilot.name}' history"):
            try:
                analyze(pilot, new_rows)  # month checks before anything is written
                save_history(conn, pilot, new_rows)
                st.success(f"Imported {len(new_rows)} month(s).")
            except ValidationError as e:
                show_problems("This CSV was not imported:", e)
                st.stop()
    actuals = get_actuals(conn, pilot.name)
    st.caption(f"{len(actuals)} month(s) stored for '{pilot.name}'.")

if not actuals:
    st.info("Import a monthly CSV (or switch the sample toggle on) to see the dashboard.")
    st.stop()

# ---------------------------------------------------------------------------
# Step 3 — dashboard
# ---------------------------------------------------------------------------
st.header("3. Dashboard")

try:
    analysis = analyze(pilot, actuals)
except ValidationError as e:
    show_problems("The stored months do not fit this pilot:", e)
    st.stop()
summary = build_summary(analysis)

for w in summary.warnings:
    st.warning(w)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Realization rate", fmt_pct(summary.realization_rate))
m2.metric("Cost / successful outcome", fmt_money2(summary.cost_per_outcome))
m3.metric("Cumulative net value", fmt_money(summary.cumulative_net_value))
if summary.payback_status == PAYBACK_LOST:
    m4.metric("Payback", f"{summary.payback_month} (lost)")
else:
    m4.metric("Payback", summary.payback_month or "not yet")

# Promised vs realized hours by month.
st.subheader("Promised vs. realized hours by month")
st.bar_chart(
    {
        "Promised": {r.month: r.promised_hours for r in analysis.months},
        "Realized": {r.month: r.realized_hours for r in analysis.months},
    }
)

# Cumulative net value trend.
st.subheader("Cumulative net value by month")
st.line_chart({r.month: r.cumulative_net_value for r in analysis.months})

# Monthly table.
st.subheader("Monthly table")
st.dataframe(
    [
        {
            "month": r.month,
            "realized hrs": r.realized_hours,
            "promised hrs": r.promised_hours,
            "realization": fmt_pct(r.realization_rate),
            "success rate": fmt_pct(r.success_rate),
            "adoption": fmt_pct(r.adoption_rate),
            "cost/outcome": fmt_money2(r.cost_per_successful_outcome),
            "net value": fmt_money(r.net_value),
            "cumulative": fmt_money(r.cumulative_net_value),
        }
        for r in analysis.months
    ],
    use_container_width=True,
    hide_index=True,
)

# Leak check + executive summary.
st.subheader(f"Value leaks as of {summary.leak_window}")
st.markdown(f"**{leak_headline(summary)}**")
badge_color = {"Red": "🔴", "Yellow": "🟡", "Green": "🟢", "n/a": "⚪"}
for i, leak in enumerate(summary.leaks, 1):
    st.markdown(
        f"**{i}. {badge_color.get(leak.status, '⚪')} {leak.kind.title()} "
        f"({leak.status})** — {leak.message}"
    )
    if leak.trend:
        st.caption(f"Trend: {leak.trend}")
    st.markdown(f"&nbsp;&nbsp;&nbsp;*Fix:* {leak.fix}")

st.subheader("Executive summary")
st.text(render_text(summary))

# Narration: one API call per distinct set of figures, only on request.
facts_key = hashlib.sha256(
    json.dumps(facts_from_summary(summary), sort_keys=True).encode()
).hexdigest()
narrations = st.session_state.setdefault("narrations", {})

if os.environ.get("ANTHROPIC_API_KEY"):
    if facts_key not in narrations and st.button("Narrate with Claude"):
        narrations[facts_key] = narrate(summary)
        if narrations[facts_key] is None:
            st.caption("Narration unavailable; the rule-based summary above is complete.")
else:
    st.caption("Set ANTHROPIC_API_KEY to add an optional Claude-narrated paragraph.")

prose = narrations.get(facts_key)
if prose:
    st.caption("Narrated by Claude — every figure was inserted by ValueGap, not written by the model.")
    st.write(prose)

st.download_button(
    "Download HTML executive summary",
    data=render_html(summary, narrated_prose=prose),
    file_name=f"valuegap_summary_{pilot.name.replace(' ', '_')}.html",
    mime="text/html",
)
