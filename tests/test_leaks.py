"""One happy-path test per leak check, plus a zero-denominator (n/a) test each,
plus the ranking behaviour.
"""

from valuegap.calculations import MonthlyActual, Pilot, analyze
from valuegap.leaks import (
    GREEN,
    NA,
    RED,
    YELLOW,
    check_adoption,
    check_cost,
    check_quality,
    evaluate_leaks,
)


# --- adoption leak ---------------------------------------------------------
def test_adoption_green():
    assert check_adoption(0.85).status == GREEN


def test_adoption_yellow():
    assert check_adoption(0.60).status == YELLOW


def test_adoption_red():
    leak = check_adoption(0.36)
    assert leak.status == RED
    assert "36%" in leak.message  # quotes the number it was given
    assert leak.fix  # a fix is always present


def test_adoption_boundaries():
    assert check_adoption(0.80).status == GREEN   # >= 0.80 Green
    assert check_adoption(0.50).status == YELLOW  # >= 0.50 Yellow
    assert check_adoption(0.4999).status == RED


def test_adoption_zero_denominator_is_na():
    # adoption_rate returned None because eligible_users == 0.
    leak = check_adoption(None)
    assert leak.status == NA
    assert leak.value is None
    assert "no eligible users" in leak.message.lower()


# --- quality leak ----------------------------------------------------------
def test_quality_green():
    assert check_quality(0.95).status == GREEN


def test_quality_yellow():
    assert check_quality(0.80).status == YELLOW


def test_quality_red():
    assert check_quality(0.60).status == RED


def test_quality_boundaries():
    assert check_quality(0.90).status == GREEN
    assert check_quality(0.70).status == YELLOW
    assert check_quality(0.6999).status == RED


def test_quality_zero_denominator_is_na():
    leak = check_quality(None)
    assert leak.status == NA
    assert leak.value is None


# --- cost leak -------------------------------------------------------------
def test_cost_green():
    # 2.12 vs target 3.00 -> at or below -> Green
    assert check_cost(2.12, 3.00).status == GREEN


def test_cost_yellow():
    # 3.30 vs 3.00 -> 10% over, within 20% -> Yellow
    assert check_cost(3.30, 3.00).status == YELLOW


def test_cost_red():
    # 4.00 vs 3.00 -> 33% over -> Red
    assert check_cost(4.00, 3.00).status == RED


def test_cost_boundaries():
    assert check_cost(3.00, 3.00).status == GREEN   # exactly target
    assert check_cost(3.60, 3.00).status == YELLOW  # exactly 1.20x
    assert check_cost(3.61, 3.00).status == RED


def test_cost_zero_denominator_is_na():
    # cost_per_successful_outcome was None (zero successful outcomes).
    leak = check_cost(None, 3.00)
    assert leak.status == NA
    assert "zero successful outcomes" in leak.message.lower()


def test_cost_zero_target_is_na():
    # No per-outcome target because the pilot promised zero outcomes.
    leak = check_cost(2.50, None)
    assert leak.status == NA


# --- ranking ---------------------------------------------------------------
def _pilot():
    return Pilot(
        name="Drafting assistant", start_month="2026-01",
        implementation_cost=20000, value_per_hour=60,
        promised_hours_saved=200, promised_successful_outcomes=400,
        promised_success_rate=0.90, promised_ai_cost_budget=1200,
    )


def _actuals():
    rows = [
        ("2026-01", 80, 175, 190, 500, 15, 18, 50),
        ("2026-02", 120, 255, 280, 600, 12, 26, 50),
        ("2026-03", 160, 320, 350, 680, 10, 33, 50),
        ("2026-04", 200, 380, 410, 760, 8, 40, 50),
        ("2026-05", 215, 410, 440, 820, 6, 44, 50),
        ("2026-06", 225, 430, 455, 820, 5, 46, 50),
    ]
    return [MonthlyActual(*r) for r in rows]


def test_evaluate_leaks_returns_three_worst_first():
    leaks = evaluate_leaks(analyze(_pilot(), _actuals()))
    assert len(leaks) == 3
    # Sorted by severity descending.
    assert leaks[0].severity >= leaks[1].severity >= leaks[2].severity


def test_sample_arc_adoption_leak_is_fixed_by_the_latest_month():
    # Month 1: adoption is the leak. Latest month: fixed, and the trend says so.
    first = evaluate_leaks(analyze(_pilot(), _actuals()[:1]))
    assert first[0].kind == "adoption" and first[0].status == RED

    leaks = evaluate_leaks(analyze(_pilot(), _actuals()))
    adoption = next(lk for lk in leaks if lk.kind == "adoption")
    assert adoption.status == GREEN
    assert adoption.value == 46 / 50  # latest month, not the 69% average
    assert adoption.trend == "Red (36%) in 2026-01 -> Green (92%) in 2026-06"
    assert not any(lk.is_active for lk in leaks)


def test_leaks_use_latest_month_not_pilot_to_date_average():
    rows = _actuals()
    rows[-1] = MonthlyActual("2026-06", 225, 430, 455, 820, 5, 20, 50)  # adoption drops
    leaks = evaluate_leaks(analyze(_pilot(), rows))
    adoption = next(lk for lk in leaks if lk.kind == "adoption")
    assert adoption.status == RED  # 40% now, even though the average is higher
    assert leaks[0].kind == "adoption"


def test_leak_window_can_span_several_months(monkeypatch):
    from valuegap.calculations import CONFIG

    monkeypatch.setitem(CONFIG, "leak_window_months", 3)
    analysis = analyze(_pilot(), _actuals())
    assert (analysis.window_start, analysis.window_end) == ("2026-04", "2026-06")
    assert analysis.window_adoption_rate == (40 + 44 + 46) / 150


# --- quality line comes from the pilot's promise ----------------------------
def test_promised_success_rate_sets_the_quality_green_line():
    import dataclasses

    strict = dataclasses.replace(_pilot(), promised_success_rate=0.99)
    assert check_quality(0.95, _pilot()).status == GREEN
    leak = check_quality(0.95, strict)
    assert leak.status == YELLOW
    assert "99%" in leak.message


def test_quality_yellow_never_above_a_low_promise():
    import dataclasses

    lenient = dataclasses.replace(_pilot(), promised_success_rate=0.60)
    assert check_quality(0.65, lenient).status == GREEN
    assert check_quality(0.55, lenient).status == RED


def test_zero_promised_success_rate_uses_config_default():
    import dataclasses

    unset = dataclasses.replace(_pilot(), promised_success_rate=0.0)
    assert check_quality(0.85, unset).status == YELLOW  # default Green is 0.90
