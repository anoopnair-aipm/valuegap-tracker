"""Bad input stops with a clear message; friendly formats are normalised.

Covers every input case from the strict review: blanks, missing columns,
currency and thousands separators, an Excel byte-order mark, header case,
negatives, nan/inf, impossible ratios, bad or unpadded months, duplicates,
months before the pilot start, and gaps.
"""

import pytest

from valuegap.calculations import MonthlyActual, Pilot, analyze
from valuegap.storage import load_actuals_text, load_pilot_json
from valuegap.validation import ValidationError, normalize_month, parse_pilot

HDR = "month,hours_saved,successful_outcomes,total_outcomes,ai_cost,rework_hours,active_users,eligible_users\n"
GOOD_ROW = "2026-01,80,175,190,500,15,18,50\n"


def _pilot(**kw):
    base = dict(
        name="Drafting assistant", start_month="2026-01",
        implementation_cost=20000, value_per_hour=60,
        promised_hours_saved=200, promised_successful_outcomes=400,
        promised_success_rate=0.90, promised_ai_cost_budget=1200,
    )
    base.update(kw)
    return Pilot(**base)


def _problems(text):
    with pytest.raises(ValidationError) as exc:
        load_actuals_text(text)
    return "\n".join(exc.value.problems)


# --- accepted and normalised --------------------------------------------------
def test_good_csv_parses():
    [row] = load_actuals_text(HDR + GOOD_ROW)
    assert row.month == "2026-01" and row.ai_cost == 500


def test_currency_and_thousands_separators_are_accepted():
    [row] = load_actuals_text(HDR + '2026-01,80,175,190,"$1,200",15,18,50\n')
    assert row.ai_cost == 1200


def test_excel_byte_order_mark_is_accepted():
    assert load_actuals_text("﻿" + HDR + GOOD_ROW)[0].month == "2026-01"


def test_header_case_and_spaces_are_accepted():
    hdr = HDR.replace("ai_cost", " AI_Cost ").replace("month", "Month", 1)
    assert load_actuals_text(hdr + GOOD_ROW)[0].ai_cost == 500


def test_unpadded_month_is_normalised_so_it_sorts():
    rows = load_actuals_text(HDR + "2026-10,1,1,1,1,1,1,1\n2026-9,1,1,1,1,1,1,1\n")
    assert sorted(r.month for r in rows) == ["2026-09", "2026-10"]


def test_blank_trailing_line_is_ignored():
    assert len(load_actuals_text(HDR + GOOD_ROW + ",,,,,,,\n")) == 1


# --- rejected with a clear message -------------------------------------------
def test_blank_cell_is_rejected():
    assert "Row 2 (2026-01): hours_saved is blank" in _problems(HDR + "2026-01,,175,190,500,15,18,50\n")


def test_missing_column_is_rejected():
    msg = _problems("month,hours_saved\n2026-01,80\n")
    assert "missing column(s)" in msg and "successful_outcomes" in msg


def test_text_in_numeric_cell_is_rejected():
    assert "'lots' is not a number" in _problems(HDR + "2026-01,lots,175,190,500,15,18,50\n")


def test_nan_and_inf_are_rejected():
    msg = _problems(HDR + "2026-01,nan,175,190,inf,15,18,50\n")
    assert "hours_saved 'nan' is not a finite number" in msg
    assert "ai_cost 'inf' is not a finite number" in msg


def test_negative_values_are_rejected():
    msg = _problems(HDR + "2026-01,-80,175,190,-500,15,18,50\n")
    assert "hours_saved -80 is negative" in msg
    assert "ai_cost -500 is negative" in msg


def test_successful_more_than_total_is_rejected():
    assert "successful_outcomes (500) is more than total_outcomes (190)" in _problems(
        HDR + "2026-01,80,500,190,500,15,18,50\n"
    )


def test_active_more_than_eligible_is_rejected():
    assert "active_users (90) is more than eligible_users (50)" in _problems(
        HDR + "2026-01,80,175,190,500,15,90,50\n"
    )


def test_free_text_month_is_rejected():
    assert "'Jan 2026' is not a month; use YYYY-MM" in _problems(
        HDR + "Jan 2026,80,175,190,500,15,18,50\n"
    )


def test_month_thirteen_is_rejected():
    with pytest.raises(ValueError):
        normalize_month("2026-13")


def test_all_row_problems_reported_together():
    msg = _problems(HDR + "2026-01,,175,190,500,15,18,50\n2026-02,80,175,190,-1,15,18,50\n")
    assert "Row 2" in msg and "Row 3" in msg


# --- month checks against the pilot -----------------------------------------
def test_duplicate_months_are_rejected():
    rows = load_actuals_text(HDR + GOOD_ROW + GOOD_ROW)
    with pytest.raises(ValidationError, match="2026-01 appears more than once"):
        analyze(_pilot(), rows)


def test_month_before_pilot_start_is_rejected():
    rows = [MonthlyActual("2025-12", 1, 1, 1, 1, 1, 1, 1)]
    with pytest.raises(ValidationError, match="before the pilot's start month"):
        analyze(_pilot(), rows)


def test_missing_months_are_a_warning_not_an_error():
    rows = [MonthlyActual("2026-01", 1, 1, 1, 1, 1, 1, 1),
            MonthlyActual("2026-04", 1, 1, 1, 1, 1, 1, 1)]
    analysis = analyze(_pilot(), rows)
    assert len(analysis.warnings) == 1
    assert "No actuals for 2026-02, 2026-03" in analysis.warnings[0]


def test_missing_months_appear_in_the_summary():
    from valuegap.report import build_summary, render_text

    rows = [MonthlyActual("2026-02", 1, 1, 1, 1, 1, 1, 1)]
    text = render_text(build_summary(analyze(_pilot(), rows)))
    assert "Data notes:" in text and "No actuals for 2026-01" in text


# --- pilot definition ----------------------------------------------------------
def test_pilot_missing_field_is_rejected():
    with pytest.raises(ValidationError, match="'start_month' is missing"):
        parse_pilot({"name": "x", "implementation_cost": 1, "value_per_hour": 1,
                     "promised_hours_saved": 1, "promised_successful_outcomes": 1,
                     "promised_success_rate": 0.9, "promised_ai_cost_budget": 1})


def test_pilot_bad_start_month_is_rejected():
    raw = dict(vars(_pilot()), start_month="January")
    with pytest.raises(ValidationError, match="start_month 'January' is not a month"):
        parse_pilot(raw)


def test_pilot_success_rate_as_percent_is_rejected():
    raw = dict(vars(_pilot()), promised_success_rate=90)
    with pytest.raises(ValidationError, match="as a fraction between 0 and 1"):
        parse_pilot(raw)


def test_pilot_json_that_is_not_json_is_rejected(tmp_path):
    p = tmp_path / "pilot.json"
    p.write_text("{not json")
    with pytest.raises(ValidationError, match="not valid JSON"):
        load_pilot_json(p)


def test_shipped_sample_pilot_is_valid():
    from pathlib import Path

    pilot = load_pilot_json(Path(__file__).parents[1] / "data" / "sample_pilot.json")
    assert pilot.target_cost_per_outcome == pytest.approx(3.0)
