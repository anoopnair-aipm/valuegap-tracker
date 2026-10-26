"""Input validation for pilot definitions and monthly actuals.

Bad input should stop the tool with a clear, row-level message — never a raw
traceback, and never a silently wrong number in an executive summary. Two
layers:

* :func:`parse_pilot` / :func:`parse_actuals_rows` check each field: present,
  numeric, finite, not negative, months in ``YYYY-MM``. Friendly inputs are
  normalised rather than rejected: ``$500``, ``"1,200"``, header case and
  whitespace, an Excel byte-order mark, and ``2026-9`` -> ``2026-09``.
* :func:`check_months` checks the actuals against the pilot: no duplicate
  months, nothing before the pilot's start month (errors), and gaps in the
  month sequence (warnings — the summary says which months are missing).

All problems found are reported together in one :class:`ValidationError`, so a
pilot owner can fix a CSV in one pass.
"""

from __future__ import annotations

import math
import re
from typing import Iterable

from .calculations import MonthlyActual, Pilot

ACTUALS_COLUMNS = (
    "month",
    "hours_saved",
    "successful_outcomes",
    "total_outcomes",
    "ai_cost",
    "rework_hours",
    "active_users",
    "eligible_users",
)

PILOT_NUMERIC_FIELDS = (
    "implementation_cost",
    "value_per_hour",
    "promised_hours_saved",
    "promised_successful_outcomes",
    "promised_success_rate",
    "promised_ai_cost_budget",
)

_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


class ValidationError(ValueError):
    """One or more input problems, each a plain-language line."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


# ---------------------------------------------------------------------------
# Field-level helpers
# ---------------------------------------------------------------------------
def normalize_month(raw: str) -> str:
    """Return ``raw`` as ``YYYY-MM``; raise ``ValueError`` if it is not a month.

    ``2026-9`` is accepted and padded to ``2026-09`` so months sort correctly."""
    m = _MONTH_RE.match(str(raw).strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ValueError(f"'{raw}' is not a month; use YYYY-MM, e.g. 2026-01")
    return f"{m.group(1)}-{int(m.group(2)):02d}"


def parse_number(raw: object) -> float:
    """Parse a numeric cell. Accepts ``$`` and thousands separators.

    Rejects blanks, text, ``nan`` and ``inf``, and negative values — none of
    the inputs ValueGap tracks can be negative."""
    text = str(raw if raw is not None else "").strip().replace("$", "").replace(",", "")
    if text == "":
        raise ValueError("is blank")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"'{raw}' is not a number") from None
    if not math.isfinite(value):
        raise ValueError(f"'{raw}' is not a finite number")
    if value < 0:
        raise ValueError(f"{raw} is negative")
    return value


def _normalize_keys(row: dict) -> dict:
    """Lower-case, strip, and drop a byte-order mark from header names."""
    return {
        str(k).replace("﻿", "").strip().lower(): v
        for k, v in row.items()
        if k is not None
    }


def month_range(first: str, last: str) -> list[str]:
    """Every ``YYYY-MM`` month from ``first`` to ``last`` inclusive."""
    y, m = int(first[:4]), int(first[5:])
    out = []
    while f"{y}-{m:02d}" <= last:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# ---------------------------------------------------------------------------
# Pilot
# ---------------------------------------------------------------------------
def parse_pilot(raw: dict) -> Pilot:
    """Validate a pilot definition dict and return a :class:`Pilot`."""
    d = _normalize_keys(raw)
    problems: list[str] = []

    name = str(d.get("name") or "").strip()
    if not name:
        problems.append("Pilot: 'name' is missing or blank.")

    start_month = ""
    if "start_month" not in d:
        problems.append("Pilot: 'start_month' is missing.")
    else:
        try:
            start_month = normalize_month(d["start_month"])
        except ValueError as e:
            problems.append(f"Pilot: start_month {e}.")

    values: dict[str, float] = {}
    for f in PILOT_NUMERIC_FIELDS:
        if f not in d:
            problems.append(f"Pilot: '{f}' is missing.")
            continue
        try:
            values[f] = parse_number(d[f])
        except ValueError as e:
            problems.append(f"Pilot: {f} {e}.")

    rate = values.get("promised_success_rate")
    if rate is not None and rate > 1:
        problems.append(
            f"Pilot: promised_success_rate is {rate}; enter it as a fraction "
            "between 0 and 1 (e.g. 0.90)."
        )

    if problems:
        raise ValidationError(problems)
    return Pilot(name=name, start_month=start_month, **values)


# ---------------------------------------------------------------------------
# Monthly actuals
# ---------------------------------------------------------------------------
def parse_actuals_rows(rows: Iterable[dict]) -> list[MonthlyActual]:
    """Validate CSV rows (dicts keyed by header) into :class:`MonthlyActual`.

    Row numbers in messages are spreadsheet rows: the header is row 1."""
    problems: list[str] = []
    actuals: list[MonthlyActual] = []

    for row_no, raw in enumerate(rows, start=2):
        row = _normalize_keys(raw)
        if row_no == 2:
            missing = [c for c in ACTUALS_COLUMNS if c not in row]
            if missing:
                raise ValidationError(
                    [f"CSV is missing column(s): {', '.join(missing)}. "
                     f"Expected: {', '.join(ACTUALS_COLUMNS)}."]
                )
        if all(str(v or "").strip() == "" for v in row.values()):
            continue  # tolerate blank trailing lines

        row_problems: list[str] = []
        try:
            month = normalize_month(row["month"])
        except ValueError as e:
            row_problems.append(f"Row {row_no}: month {e}.")
            month = str(row["month"])

        nums: dict[str, float] = {}
        for col in ACTUALS_COLUMNS[1:]:
            try:
                nums[col] = parse_number(row[col])
            except ValueError as e:
                row_problems.append(f"Row {row_no} ({month}): {col} {e}.")

        if not row_problems:
            if nums["successful_outcomes"] > nums["total_outcomes"]:
                row_problems.append(
                    f"Row {row_no} ({month}): successful_outcomes "
                    f"({nums['successful_outcomes']:g}) is more than "
                    f"total_outcomes ({nums['total_outcomes']:g})."
                )
            if nums["active_users"] > nums["eligible_users"]:
                row_problems.append(
                    f"Row {row_no} ({month}): active_users "
                    f"({nums['active_users']:g}) is more than "
                    f"eligible_users ({nums['eligible_users']:g})."
                )

        if row_problems:
            problems.extend(row_problems)
        else:
            actuals.append(MonthlyActual(month=month, **nums))

    if problems:
        raise ValidationError(problems)
    return actuals


def check_months(pilot: Pilot, actuals: list[MonthlyActual]) -> list[str]:
    """Check actuals against the pilot. Raise on errors, return warnings.

    Errors: a month reported twice, or a month before the pilot's start.
    Warnings: months missing between the start month and the latest month."""
    problems: list[str] = []
    seen: set[str] = set()
    for a in actuals:
        if a.month in seen:
            problems.append(
                f"Month {a.month} appears more than once; keep one row per month."
            )
        seen.add(a.month)
        if a.month < pilot.start_month:
            problems.append(
                f"Month {a.month} is before the pilot's start month "
                f"({pilot.start_month})."
            )
    if problems:
        raise ValidationError(sorted(set(problems)))

    if not actuals:
        return []
    expected = month_range(pilot.start_month, max(seen))
    missing = [m for m in expected if m not in seen]
    if not missing:
        return []
    return [
        f"No actuals for {', '.join(missing)}. Those months are left out of "
        "promised-vs-realized and net value until they are entered."
    ]
