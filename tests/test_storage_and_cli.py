"""SQLite history and the command-line entry point."""

import sqlite3
from pathlib import Path

import pytest

from valuegap.calculations import MonthlyActual
from valuegap.check import main
from valuegap.storage import (
    connect,
    get_actuals,
    get_pilot,
    load_actuals_csv,
    load_pilot_json,
    save_actual,
    save_history,
)

DATA = Path(__file__).parents[1] / "data"
PILOT = str(DATA / "sample_pilot.json")
ACTUALS = str(DATA / "sample_monthly.csv")
HDR = "month,hours_saved,successful_outcomes,total_outcomes,ai_cost,rework_hours,active_users,eligible_users\n"


# --- storage ---------------------------------------------------------------
def test_history_round_trip_and_reimport_upserts(tmp_path):
    conn = connect(str(tmp_path / "v.db"))
    pilot = load_pilot_json(PILOT)
    actuals = load_actuals_csv(ACTUALS)
    assert len(save_history(conn, pilot, actuals)) == 6
    assert len(save_history(conn, pilot, actuals[:1])) == 6  # same month again -> replaced
    assert get_pilot(conn, pilot.name) == pilot


def test_foreign_key_blocks_actuals_for_unknown_pilot(tmp_path):
    conn = connect(str(tmp_path / "v.db"))
    with pytest.raises(sqlite3.IntegrityError):
        save_actual(conn, "ghost", MonthlyActual("2026-01", 1, 1, 1, 1, 1, 1, 1))


def test_history_persists_across_connections(tmp_path):
    db = str(tmp_path / "v.db")
    pilot = load_pilot_json(PILOT)
    save_history(connect(db), pilot, load_actuals_csv(ACTUALS)[:3])
    assert [a.month for a in get_actuals(connect(db), pilot.name)] == [
        "2026-01", "2026-02", "2026-03",
    ]


# --- CLI ---------------------------------------------------------------------
def test_cli_prints_headline_figures(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["--pilot", PILOT, "--actuals", ACTUALS]) == 0
    out = capsys.readouterr().out
    for s in ("83% of the promise", "$2.12", "$32,460", "paid back in 2026-04"):
        assert s in out


def test_cli_writes_html(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "r" / "summary.html"
    assert main(["--pilot", PILOT, "--actuals", ACTUALS, "--html", str(out), "--narrate"]) == 0
    html = out.read_text()
    assert "Value leaks as of 2026-06" in html
    assert "Executive narration" not in html  # no key -> no narration block


def test_cli_db_accumulates_months_across_runs(tmp_path, capsys):
    db = str(tmp_path / "v.db")
    first = tmp_path / "m1.csv"
    first.write_text(HDR + "2026-01,80,175,190,500,15,18,50\n")
    second = tmp_path / "m2.csv"
    second.write_text(HDR + "2026-02,120,255,280,600,12,26,50\n")
    assert main(["--pilot", PILOT, "--actuals", str(first), "--db", db]) == 0
    capsys.readouterr()
    assert main(["--pilot", PILOT, "--actuals", str(second), "--db", db]) == 0
    out = capsys.readouterr().out
    assert "200 realized against 400 promised" in out  # both months, from history


def test_cli_bad_csv_is_a_clean_error(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("month,hours_saved\n2026-01,80\n")
    assert main(["--pilot", PILOT, "--actuals", str(bad)]) == 2
    err = capsys.readouterr().err
    assert "missing column(s)" in err
    assert "Traceback" not in err


def test_cli_missing_file_is_a_clean_error(capsys):
    assert main(["--pilot", "nope.json", "--actuals", ACTUALS]) == 2
    assert "No such file or directory: nope.json" in capsys.readouterr().err


def test_cli_incomplete_pilot_is_a_clean_error(tmp_path, capsys):
    p = tmp_path / "p.json"
    p.write_text('{"name": "x"}')
    assert main(["--pilot", str(p), "--actuals", ACTUALS]) == 2
    assert "'start_month' is missing" in capsys.readouterr().err


def test_cli_duplicate_month_is_a_clean_error(tmp_path, capsys):
    dup = tmp_path / "dup.csv"
    dup.write_text(HDR + "2026-01,80,175,190,500,15,18,50\n" * 2)
    assert main(["--pilot", PILOT, "--actuals", str(dup)]) == 2
    assert "appears more than once" in capsys.readouterr().err
