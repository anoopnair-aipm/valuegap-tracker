"""SQLite persistence for pilots and their monthly actuals.

Standard-library ``sqlite3`` only. One pilot per name; monthly actuals are
keyed by (pilot, month) so re-importing a month overwrites it rather than
duplicating. Nothing here reaches the network — storage is entirely local.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Optional

from .calculations import MonthlyActual, Pilot
from .validation import ValidationError, parse_actuals_rows, parse_pilot

DEFAULT_DB = "valuegap.db"


def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # SQLite leaves foreign keys off unless asked, per connection.
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pilots (
            name                        TEXT PRIMARY KEY,
            start_month                 TEXT NOT NULL,
            implementation_cost         REAL NOT NULL,
            value_per_hour              REAL NOT NULL,
            promised_hours_saved        REAL NOT NULL,
            promised_successful_outcomes REAL NOT NULL,
            promised_success_rate       REAL NOT NULL,
            promised_ai_cost_budget     REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS monthly_actuals (
            pilot_name          TEXT NOT NULL,
            month               TEXT NOT NULL,
            hours_saved         REAL NOT NULL,
            successful_outcomes REAL NOT NULL,
            total_outcomes      REAL NOT NULL,
            ai_cost             REAL NOT NULL,
            rework_hours        REAL NOT NULL,
            active_users        REAL NOT NULL,
            eligible_users      REAL NOT NULL,
            PRIMARY KEY (pilot_name, month),
            FOREIGN KEY (pilot_name) REFERENCES pilots(name)
        );
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Pilots
# ---------------------------------------------------------------------------
def save_pilot(conn: sqlite3.Connection, pilot: Pilot) -> None:
    conn.execute(
        """
        INSERT INTO pilots (name, start_month, implementation_cost, value_per_hour,
            promised_hours_saved, promised_successful_outcomes,
            promised_success_rate, promised_ai_cost_budget)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            start_month=excluded.start_month,
            implementation_cost=excluded.implementation_cost,
            value_per_hour=excluded.value_per_hour,
            promised_hours_saved=excluded.promised_hours_saved,
            promised_successful_outcomes=excluded.promised_successful_outcomes,
            promised_success_rate=excluded.promised_success_rate,
            promised_ai_cost_budget=excluded.promised_ai_cost_budget
        """,
        (
            pilot.name,
            pilot.start_month,
            pilot.implementation_cost,
            pilot.value_per_hour,
            pilot.promised_hours_saved,
            pilot.promised_successful_outcomes,
            pilot.promised_success_rate,
            pilot.promised_ai_cost_budget,
        ),
    )
    conn.commit()


def get_pilot(conn: sqlite3.Connection, name: str) -> Optional[Pilot]:
    row = conn.execute(
        "SELECT * FROM pilots WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        return None
    return Pilot.from_dict(dict(row))


def list_pilots(conn: sqlite3.Connection) -> list[str]:
    return [r["name"] for r in conn.execute("SELECT name FROM pilots ORDER BY name")]


# ---------------------------------------------------------------------------
# Monthly actuals
# ---------------------------------------------------------------------------
def save_actual(
    conn: sqlite3.Connection, pilot_name: str, actual: MonthlyActual
) -> None:
    conn.execute(
        """
        INSERT INTO monthly_actuals (pilot_name, month, hours_saved,
            successful_outcomes, total_outcomes, ai_cost, rework_hours,
            active_users, eligible_users)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pilot_name, month) DO UPDATE SET
            hours_saved=excluded.hours_saved,
            successful_outcomes=excluded.successful_outcomes,
            total_outcomes=excluded.total_outcomes,
            ai_cost=excluded.ai_cost,
            rework_hours=excluded.rework_hours,
            active_users=excluded.active_users,
            eligible_users=excluded.eligible_users
        """,
        (
            pilot_name,
            actual.month,
            actual.hours_saved,
            actual.successful_outcomes,
            actual.total_outcomes,
            actual.ai_cost,
            actual.rework_hours,
            actual.active_users,
            actual.eligible_users,
        ),
    )
    conn.commit()


def get_actuals(
    conn: sqlite3.Connection, pilot_name: str
) -> list[MonthlyActual]:
    rows = conn.execute(
        "SELECT * FROM monthly_actuals WHERE pilot_name = ? ORDER BY month",
        (pilot_name,),
    ).fetchall()
    return [MonthlyActual.from_row(dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# File loaders (used by the CLI and the Streamlit importer)
# ---------------------------------------------------------------------------
def save_history(
    conn: sqlite3.Connection, pilot: Pilot, actuals: list[MonthlyActual]
) -> list[MonthlyActual]:
    """Save the pilot, upsert these months, and return its full stored history."""
    save_pilot(conn, pilot)
    for a in actuals:
        save_actual(conn, pilot.name, a)
    return get_actuals(conn, pilot.name)


def load_pilot_json(path: str | Path) -> Pilot:
    """Read and validate a pilot definition JSON file."""
    with open(path, "r", encoding="utf-8-sig") as fh:
        try:
            raw = json.load(fh)
        except json.JSONDecodeError as e:
            raise ValidationError([f"Pilot file is not valid JSON: {e}"]) from None
    if not isinstance(raw, dict):
        raise ValidationError(["Pilot file must hold one JSON object."])
    return parse_pilot(raw)


def load_actuals_text(text: str) -> list[MonthlyActual]:
    """Parse and validate monthly actuals from CSV text with a header row.

    Expected columns: month, hours_saved, successful_outcomes, total_outcomes,
    ai_cost, rework_hours, active_users, eligible_users."""
    text = text.lstrip("﻿")  # Excel's UTF-8 byte-order mark
    return parse_actuals_rows(csv.DictReader(io.StringIO(text)))


def load_actuals_csv(path: str | Path) -> list[MonthlyActual]:
    """Read and validate monthly actuals from a CSV file."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return load_actuals_text(fh.read())
