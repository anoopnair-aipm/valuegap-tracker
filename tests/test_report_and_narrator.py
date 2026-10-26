"""The rule-based summary must be complete with NO API key and handle n/a
gracefully; the narrator must fall back silently and can never put a number
into the prose that code did not put there.
"""

import sys
import types

import pytest

from valuegap import narrator
from valuegap.calculations import MonthlyActual, Pilot, analyze
from valuegap.narrator import check_template, facts_from_summary, fill_template, narrate
from valuegap.report import build_summary, render_html, render_text


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


def _summary():
    return build_summary(analyze(_pilot(), _actuals()))


# --- rule-based summary ----------------------------------------------------
def test_text_summary_complete_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text = render_text(_summary())
    assert "Promised vs. realized hours" in text
    assert "Cost per successful outcome" in text
    assert "Cumulative net value" in text
    assert "Payback: paid back in 2026-04." in text
    assert "Value leaks as of 2026-06" in text
    assert text.count("Fix:") == 3


def test_html_summary_generates_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = render_html(_summary())
    assert out.lstrip().startswith("<!doctype html>")
    assert "Value leaks as of 2026-06" in out
    assert "Trend:" in out


def test_summary_handles_zero_denominators_as_na():
    pilot = Pilot(
        name="Edge", start_month="2026-01", implementation_cost=0,
        value_per_hour=50, promised_hours_saved=0,
        promised_successful_outcomes=0, promised_success_rate=0.0,
        promised_ai_cost_budget=0,
    )
    summary = build_summary(analyze(pilot, [MonthlyActual("2026-01", 0, 0, 0, 0, 0, 0, 0)]))
    text = render_text(summary)
    assert "n/a" in text
    assert "cannot be scored yet" in text
    assert render_html(summary).lstrip().startswith("<!doctype html>")


def test_payback_wording_not_doubled():
    rows = [MonthlyActual("2026-01", 10, 10, 10, 0, 0, 1, 1)]
    text = render_text(build_summary(analyze(_pilot(), rows)))
    assert "Payback: not yet reached." in text


# --- narrator: template guard -----------------------------------------------
def test_template_with_placeholders_only_is_accepted():
    facts = facts_from_summary(_summary())
    t = ("{pilot_name} realized {realization_rate} of the promise at "
         "{cost_per_outcome} per outcome; net value is {cumulative_net_value} "
         "and it {payback}. One fix: {leak1_fix}")
    assert check_template(t, facts) is None
    out = fill_template(t, facts)
    assert "83%" in out and "$2.12" in out and "$32,460" in out
    assert "paid back in 2026-04" in out


def test_template_with_a_digit_is_rejected():
    facts = facts_from_summary(_summary())
    t = ("Realized 90% ({realization_rate}) at {cost_per_outcome}; "
         "{cumulative_net_value}; {payback}.")
    assert "number outside" in check_template(t, facts)


def test_template_with_spelled_out_number_is_rejected():
    facts = facts_from_summary(_summary())
    t = ("Eighty percent realized: {realization_rate}, {cost_per_outcome}, "
         "{cumulative_net_value}, {payback}.")
    assert "spelled-out" in check_template(t, facts)


def test_template_with_unknown_placeholder_is_rejected():
    facts = facts_from_summary(_summary())
    t = "{realization_rate} {cost_per_outcome} {cumulative_net_value} {payback} {roi}"
    assert "unknown placeholder" in check_template(t, facts)


def test_template_missing_required_figure_is_rejected():
    facts = facts_from_summary(_summary())
    t = "{realization_rate} at {cost_per_outcome}."
    assert "missing required" in check_template(t, facts)


# --- narrator: end to end with a fake client --------------------------------
def _fake_anthropic(monkeypatch, reply, *, stop_reason="end_turn", raises=None):
    """Install a fake `anthropic` module whose client returns ``reply``."""
    calls = []

    class Block:
        type = "text"

        def __init__(self, text):
            self.text = text

    class Resp:
        def __init__(self, text):
            self.content = [Block(text)]
            self.stop_reason = stop_reason

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            if raises:
                raise raises
            return Resp(reply)

    class Client:
        def __init__(self, **kwargs):
            self.messages = Messages()
            self.beta = types.SimpleNamespace(messages=self.messages)

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    return calls


GOOD = ("{pilot_name} has realized {realization_rate} of its promised hours at "
        "{cost_per_outcome} per successful outcome. Cumulative net value is "
        "{cumulative_net_value}, and the pilot {payback}. {leak_headline}")


def test_narrator_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert narrate(_summary()) is None


def test_narrator_faithful_rewrite_succeeds(monkeypatch):
    calls = _fake_anthropic(monkeypatch, GOOD)
    out = narrate(_summary())
    assert out is not None
    assert "83%" in out and "$2.12" in out and "$32,460" in out
    assert len(calls) == 1
    assert calls[0]["model"] == narrator.DEFAULT_MODEL
    assert calls[0]["output_config"] == {"effort": "low"}
    assert calls[0]["fallbacks"] == "default"


def test_narrator_rejects_model_written_numbers(monkeypatch):
    # The swap attack from the review: the model writes figures itself.
    _fake_anthropic(monkeypatch, "Cost is $3.00 against a $2.12 target. " + GOOD)
    assert narrate(_summary()) is None


def test_narrator_falls_back_on_api_error(monkeypatch):
    _fake_anthropic(monkeypatch, GOOD, raises=RuntimeError("network down"))
    assert narrate(_summary()) is None


def test_narrator_falls_back_on_refusal(monkeypatch):
    _fake_anthropic(monkeypatch, GOOD, stop_reason="refusal")
    assert narrate(_summary()) is None


def test_narrator_model_override_skips_fallbacks(monkeypatch):
    calls = _fake_anthropic(monkeypatch, GOOD)
    monkeypatch.setenv("VALUEGAP_NARRATOR_MODEL", "claude-haiku-5-5")
    assert narrate(_summary()) is not None
    assert calls[0]["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in calls[0]
