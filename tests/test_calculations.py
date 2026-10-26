"""One happy-path test per calculation, plus a zero-denominator test per rate.

Zero-denominator cases must return None (rendered "n/a") and never raise,
inf, or NaN.
"""

import math

import pytest

from valuegap.calculations import (
    PAYBACK_LOST,
    PAYBACK_NOT_REACHED,
    PAYBACK_REACHED,
    MonthlyActual,
    Pilot,
    adoption_rate,
    analyze,
    cost_per_successful_outcome,
    cumulative_net_value,
    net_monthly_value,
    payback_month,
    payback_status,
    realization_rate,
    success_rate,
)


# --- realization rate ------------------------------------------------------
def test_realization_rate_happy():
    assert realization_rate(80, 200) == pytest.approx(0.4)


def test_realization_rate_zero_denominator():
    # Nothing promised -> undefined, not a crash.
    assert realization_rate(50, 0) is None


# --- success rate ----------------------------------------------------------
def test_success_rate_happy():
    assert success_rate(175, 190) == pytest.approx(175 / 190)


def test_success_rate_zero_denominator():
    assert success_rate(0, 0) is None


# --- adoption rate ---------------------------------------------------------
def test_adoption_rate_happy():
    assert adoption_rate(18, 50) == pytest.approx(0.36)


def test_adoption_rate_zero_denominator():
    assert adoption_rate(10, 0) is None


# --- cost per successful outcome ------------------------------------------
def test_cost_per_successful_outcome_happy():
    assert cost_per_successful_outcome(500, 175) == pytest.approx(500 / 175)


def test_cost_per_successful_outcome_zero_denominator():
    # Dollars per nothing is undefined, not infinite.
    result = cost_per_successful_outcome(500, 0)
    assert result is None
    # Guard against a regression that returns inf/nan instead of None.
    assert result is None or (not math.isinf(result) and not math.isnan(result))


# --- net monthly value -----------------------------------------------------
def test_net_monthly_value_happy():
    # 80h * $60 - $500 - 15h * $60 = 4800 - 500 - 900 = 3400
    assert net_monthly_value(80, 60, 500, 15) == pytest.approx(3400)


def test_net_monthly_value_gross_hours_rework_subtracted_once():
    # hours_saved is gross; rework is subtracted separately, not pre-removed.
    with_rework = net_monthly_value(100, 50, 200, 10)
    without_rework = net_monthly_value(100, 50, 200, 0)
    assert without_rework - with_rework == pytest.approx(10 * 50)


# --- cumulative net value --------------------------------------------------
def test_cumulative_net_value_happy():
    assert cumulative_net_value([3400, 5880, 8320], 20000) == pytest.approx(-2400)


def test_cumulative_net_value_empty():
    # No months yet -> just the sunk one-time cost.
    assert cumulative_net_value([], 20000) == pytest.approx(-20000)


# --- payback month ---------------------------------------------------------
def test_payback_month_happy():
    months = ["2026-01", "2026-02", "2026-03", "2026-04"]
    cumulative = [-16600, -10720, -2400, 8360]
    assert payback_month(months, cumulative) == "2026-04"


def test_payback_month_not_reached():
    months = ["2026-01", "2026-02"]
    cumulative = [-16600, -10720]
    assert payback_month(months, cumulative) is None


def test_payback_status_states():
    assert payback_status([-5, 3, 8]) == PAYBACK_REACHED
    assert payback_status([-5, 3, -1]) == PAYBACK_LOST
    assert payback_status([-5, -3]) == PAYBACK_NOT_REACHED
    assert payback_status([]) == PAYBACK_NOT_REACHED


def test_payback_reached_then_lost_is_reported_as_lost():
    from valuegap.report import build_summary, render_text

    pilot = _sample_pilot()
    rows = [
        MonthlyActual("2026-01", 400, 175, 190, 500, 0, 40, 50),   # +23,500 -> pays back
        MonthlyActual("2026-02", 0, 175, 190, 9000, 0, 40, 50),    # -9,000 -> lost
    ]
    analysis = analyze(pilot, rows)
    assert analysis.payback_month == "2026-01"
    assert analysis.payback_status == PAYBACK_LOST
    assert analysis.cumulative_net_value == pytest.approx(-5500)
    text = render_text(build_summary(analysis))
    assert "reached in 2026-01, but cumulative net value has since fallen back below zero" in text


# --- analyze over the sample-shaped data ----------------------------------
def _sample_pilot():
    return Pilot(
        name="Drafting assistant",
        start_month="2026-01",
        implementation_cost=20000,
        value_per_hour=60,
        promised_hours_saved=200,
        promised_successful_outcomes=400,
        promised_success_rate=0.90,
        promised_ai_cost_budget=1200,
    )


def _sample_actuals():
    rows = [
        ("2026-01", 80, 175, 190, 500, 15, 18, 50),
        ("2026-02", 120, 255, 280, 600, 12, 26, 50),
        ("2026-03", 160, 320, 350, 680, 10, 33, 50),
        ("2026-04", 200, 380, 410, 760, 8, 40, 50),
        ("2026-05", 215, 410, 440, 820, 6, 44, 50),
        ("2026-06", 225, 430, 455, 820, 5, 46, 50),
    ]
    return [
        MonthlyActual(m, h, s, t, c, r, a, e) for (m, h, s, t, c, r, a, e) in rows
    ]


def test_analyze_headline_numbers():
    analysis = analyze(_sample_pilot(), _sample_actuals())
    assert analysis.realized_hours_total == pytest.approx(1000)
    assert analysis.promised_hours_total == pytest.approx(1200)
    assert analysis.realization_rate_total == pytest.approx(1000 / 1200)
    assert analysis.target_cost_per_outcome == pytest.approx(3.0)
    # Demo arc: pays back in month 4.
    assert analysis.payback_month == "2026-04"
    assert analysis.cumulative_net_value > 0


def test_analyze_sorts_months_regardless_of_input_order():
    rows = list(reversed(_sample_actuals()))
    analysis = analyze(_sample_pilot(), rows)
    assert [m.month for m in analysis.months] == [
        "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
    ]
    assert analysis.payback_month == "2026-04"


def test_analyze_with_zero_denominator_rows_does_not_crash():
    # A degenerate month: no outcomes, no eligible users, nothing promised-ish.
    pilot = Pilot(
        name="Edge", start_month="2026-01", implementation_cost=0,
        value_per_hour=50, promised_hours_saved=0,
        promised_successful_outcomes=0, promised_success_rate=0.0,
        promised_ai_cost_budget=0,
    )
    actuals = [MonthlyActual("2026-01", 0, 0, 0, 0, 0, 0, 0)]
    analysis = analyze(pilot, actuals)
    m = analysis.months[0]
    assert m.realization_rate is None
    assert m.success_rate is None
    assert m.adoption_rate is None
    assert m.cost_per_successful_outcome is None
    assert analysis.target_cost_per_outcome is None
