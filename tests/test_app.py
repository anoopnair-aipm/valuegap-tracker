"""Headless Streamlit tests of app.py. Skipped when streamlit is not installed."""

import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).parents[1] / "app.py")


@pytest.fixture
def at(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("VALUEGAP_DB", str(tmp_path / "test.db"))
    return AppTest.from_file(APP, default_timeout=60)


def test_history_mode_reads_months_from_sqlite(at, tmp_path):
    from valuegap.storage import connect, load_actuals_csv, load_pilot_json, save_history

    data = Path(APP).parent / "data"
    pilot = load_pilot_json(data / "sample_pilot.json")
    save_history(connect(str(tmp_path / "test.db")), pilot, load_actuals_csv(data / "sample_monthly.csv")[:4])

    at.run()
    at.toggle[0].set_value(False).run()
    assert not at.exception
    assert any("'name' is missing" in e.value for e in at.error)  # new pilot starts blank

    at.selectbox[0].set_value(pilot.name).run()
    assert not at.exception
    assert {m.label: m.value for m in at.metric}["Payback"] == "2026-04"
    assert any("Value leaks as of 2026-04" in s.value for s in at.subheader)


def test_sample_dashboard_renders(at):
    at.run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Realization rate"] == "83%"
    assert metrics["Payback"] == "2026-04"
    assert any("Value leaks as of 2026-06" in s.value for s in at.subheader)


def test_bad_start_month_shows_an_error_not_a_crash(at):
    at.run()
    at.text_input[1].set_value("January").run()
    assert not at.exception
    assert any("start_month 'January' is not a month" in e.value for e in at.error)


def test_no_api_call_without_a_button_click(monkeypatch, at):
    calls = []

    class Client:
        def __init__(self, **kw):
            self.messages = types.SimpleNamespace(create=lambda **k: calls.append(k))
            self.beta = types.SimpleNamespace(messages=self.messages)

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    at.run()
    at.number_input[0].set_value(25000.0).run()  # widget interaction -> rerun
    assert not at.exception
    assert calls == []
    assert any(b.label == "Narrate with Claude" for b in at.button)
