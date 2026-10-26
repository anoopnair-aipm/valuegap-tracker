"""Rule-based value-leak checks.

Three leaks, evaluated on the most recent ``CONFIG["leak_window_months"]``
months of an :class:`~valuegap.calculations.Analysis` — so the summary says
where value is leaking now, not on a pilot-to-date average that a fixed leak
keeps dragging down. Each leak also carries a trend from the first month to
now. Rules run first; narrative is layered on top elsewhere. Thresholds come
from ``calculations.CONFIG`` (the one tuning dict) and the pilot's own
promises, and are STARTING DEFAULTS the owner tunes, not benchmarks.

Each leak reports a status (Green / Yellow / Red), a plain-language message
that quotes the number it was given, and one concrete fix. A leak whose metric
is undefined (zero denominator) is reported as status "n/a" and ranked last,
never as a crash.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .calculations import CONFIG, Analysis, Pilot

RED = "Red"
YELLOW = "Yellow"
GREEN = "Green"
NA = "n/a"

# Severity ordering used to rank the leaks worst-first.
_STATUS_RANK = {RED: 3, YELLOW: 2, GREEN: 1, NA: 0}


@dataclass
class Leak:
    kind: str  # "adoption" | "quality" | "cost"
    status: str  # RED | YELLOW | GREEN | NA
    value: Optional[float]  # the metric, or None if undefined
    message: str  # plain language, quotes the number
    fix: str  # one concrete next step
    severity: float  # higher = worse; used for ranking
    trend: str = ""  # e.g. "Red (36%) in 2026-01 -> Green (92%) in 2026-06"

    @property
    def is_active(self) -> bool:
        """True for a real leak (Red or Yellow), not a healthy or n/a check."""
        return self.status in (RED, YELLOW)


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _money(x: Optional[float]) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


# ---------------------------------------------------------------------------
# Individual leak checks
# ---------------------------------------------------------------------------
def check_adoption(adoption: Optional[float]) -> Leak:
    """Adoption leak: active / eligible users vs CONFIG thresholds."""
    t = CONFIG["adoption"]
    if adoption is None:
        return Leak(
            kind="adoption",
            status=NA,
            value=None,
            message=(
                "Adoption cannot be measured: no eligible users were recorded, "
                "so there is nothing to divide active users by."
            ),
            fix="Record the eligible-user count for each month so adoption can be tracked.",
            severity=0.0,
        )

    if adoption >= t["green_at_or_above"]:
        status = GREEN
        message = (
            f"Adoption is healthy at {_pct(adoption)} of eligible users, "
            f"at or above the {_pct(t['green_at_or_above'])} target."
        )
        fix = "Hold adoption here; keep onboarding new eligible users as they join."
    elif adoption >= t["yellow_at_or_above"]:
        status = YELLOW
        message = (
            f"Adoption is partial at {_pct(adoption)} of eligible users, "
            f"below the {_pct(t['green_at_or_above'])} target. Saved hours "
            "cannot reach the promise while part of the team is not using it."
        )
        fix = "Find the non-users; remove the one blocker (training, access, or fit) that keeps them out."
    else:
        status = RED
        message = (
            f"Adoption is the weak point at {_pct(adoption)} of eligible users, "
            f"well below the {_pct(t['green_at_or_above'])} target. Most of the "
            "promised hours cannot be saved because most people are not using it."
        )
        fix = "Run a focused push with the first team: pick one workflow, get it used daily, then expand."

    # Severity: how far below the green target, normalized.
    gap = max(0.0, (t["green_at_or_above"] - adoption) / t["green_at_or_above"])
    return Leak("adoption", status, adoption, message, fix,
                severity=_STATUS_RANK[status] + gap)


def quality_thresholds(pilot: Optional[Pilot] = None) -> dict:
    """Green/Yellow lines for the quality leak.

    Green is the pilot's promised success rate when one is set (and
    ``CONFIG["success"]["green_from_pilot_promise"]`` is on), otherwise the
    CONFIG default. Yellow never sits above Green."""
    t = dict(CONFIG["success"])
    if (
        pilot is not None
        and t.get("green_from_pilot_promise")
        and pilot.promised_success_rate > 0
    ):
        t["green_at_or_above"] = pilot.promised_success_rate
    t["yellow_at_or_above"] = min(t["yellow_at_or_above"], t["green_at_or_above"])
    return t


def check_quality(success: Optional[float], pilot: Optional[Pilot] = None) -> Leak:
    """Quality leak: success rate vs the promised (or default) thresholds."""
    t = quality_thresholds(pilot)
    if success is None:
        return Leak(
            kind="quality",
            status=NA,
            value=None,
            message=(
                "Quality cannot be measured: no outcomes were recorded, so "
                "there is nothing to compute a success rate from."
            ),
            fix="Record successful and total outcomes each month so quality can be tracked.",
            severity=0.0,
        )

    if success >= t["green_at_or_above"]:
        status = GREEN
        message = (
            f"Quality is strong: {_pct(success)} of outcomes succeed, "
            f"at or above the {_pct(t['green_at_or_above'])} target."
        )
        fix = "Hold quality here; keep the review step that is keeping success high."
    elif success >= t["yellow_at_or_above"]:
        status = YELLOW
        message = (
            f"Quality is acceptable but not strong: {_pct(success)} of outcomes "
            f"succeed, below the {_pct(t['green_at_or_above'])} target."
        )
        fix = "Review the failing cases from one month; fix the single most common failure pattern."
    else:
        status = RED
        message = (
            f"Quality is a leak: only {_pct(success)} of outcomes succeed, "
            f"below the {_pct(t['yellow_at_or_above'])} floor. Low quality "
            "drives rework, which eats the value the hours were meant to add."
        )
        fix = "Pause expansion; fix the top failure modes before adding more users or use cases."

    gap = max(0.0, (t["green_at_or_above"] - success) / t["green_at_or_above"])
    return Leak("quality", status, success, message, fix,
                severity=_STATUS_RANK[status] + gap)


def check_cost(
    cost_per_outcome: Optional[float], target: Optional[float]
) -> Leak:
    """Cost leak: cost per successful outcome vs the per-outcome target."""
    t = CONFIG["cost"]

    if cost_per_outcome is None:
        return Leak(
            kind="cost",
            status=NA,
            value=None,
            message=(
                "Cost per successful outcome cannot be measured: there were zero "
                "successful outcomes, so there is nothing to divide the AI cost by."
            ),
            fix="Get at least some outcomes succeeding; until then, cost-efficiency is undefined, not infinite.",
            severity=0.0,
        )
    if target is None or target == 0:
        return Leak(
            kind="cost",
            status=NA,
            value=cost_per_outcome,
            message=(
                f"Cost per successful outcome is {_money(cost_per_outcome)}, but no "
                "per-outcome target is set (the pilot promised zero outcomes), so "
                "there is nothing to compare it against."
            ),
            fix="Set a promised successful-outcome count so a per-outcome cost target can be derived.",
            severity=0.0,
        )

    ratio = cost_per_outcome / target
    if ratio <= t["green_at_or_below_mult"]:
        status = GREEN
        message = (
            f"Cost is efficient: {_money(cost_per_outcome)} per successful outcome, "
            f"at or below the {_money(target)} target."
        )
        fix = "Hold here; watch cost per outcome as volume grows so it does not creep up."
    elif ratio <= t["yellow_at_or_below_mult"]:
        status = YELLOW
        over = (ratio - 1) * 100
        message = (
            f"Cost is slightly over: {_money(cost_per_outcome)} per successful "
            f"outcome, {over:.0f}% above the {_money(target)} target "
            f"(within the {int((t['yellow_at_or_below_mult'] - 1) * 100)}% tolerance)."
        )
        fix = "Trim the most expensive calls (shorter prompts, cheaper model for easy cases) to pull back under target."
    else:
        status = RED
        over = (ratio - 1) * 100
        message = (
            f"Cost is a leak: {_money(cost_per_outcome)} per successful outcome, "
            f"{over:.0f}% above the {_money(target)} target. Spend is outrunning "
            "the value each outcome returns."
        )
        fix = "Re-scope: move easy cases to a cheaper model and cut retries, then re-check cost per outcome."

    # Severity scales with how far over target it runs.
    gap = max(0.0, ratio - 1.0)
    return Leak("cost", status, cost_per_outcome, message, fix,
                severity=_STATUS_RANK[status] + gap)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------
def _fmt_value(leak: Leak) -> str:
    return _money(leak.value) if leak.kind == "cost" else _pct(leak.value)


def _check_all(adoption, success, cost, analysis: Analysis) -> list[Leak]:
    return [
        check_adoption(adoption),
        check_quality(success, analysis.pilot),
        check_cost(cost, analysis.target_cost_per_outcome),
    ]


def window_label(analysis: Analysis) -> str:
    """'2026-06' for a one-month window, '2026-04 to 2026-06' otherwise."""
    if analysis.window_start == analysis.window_end:
        return analysis.window_end or "n/a"
    return f"{analysis.window_start} to {analysis.window_end}"


def evaluate_leaks(analysis: Analysis) -> list[Leak]:
    """Evaluate all three leaks on the latest window, worst first.

    Returns exactly three checks (adoption, quality, cost) ranked by severity.
    When the pilot has more history than the window, each check carries a
    trend from the first month to now, so a fixed leak reads as fixed."""
    leaks = _check_all(
        analysis.window_adoption_rate,
        analysis.window_success_rate,
        analysis.window_cost_per_outcome,
        analysis,
    )

    if analysis.months and analysis.months[0].month != analysis.window_start:
        first = analysis.months[0]
        earlier = _check_all(
            first.adoption_rate, first.success_rate,
            first.cost_per_successful_outcome, analysis,
        )
        now = window_label(analysis)
        for leak, then in zip(leaks, earlier):
            leak.trend = (
                f"{then.status} ({_fmt_value(then)}) in {first.month} -> "
                f"{leak.status} ({_fmt_value(leak)}) in {now}"
            )

    leaks.sort(key=lambda lk: lk.severity, reverse=True)
    return leaks
