"""All ValueGap formulas and the single tuning config live here.

Design rules (so this stays the one file you edit to re-tune the tool):

* Every threshold, format, and comparison boundary is in ``CONFIG`` below.
* Every rate guards its denominator. A rate whose denominator is zero is
  genuinely undefined, so the function returns ``None`` (rendered as "n/a"
  everywhere downstream) instead of raising, or emitting ``inf`` / ``NaN``.
* ``hours_saved`` is treated as GROSS hours saved. Rework is NOT pre-subtracted
  from it; rework is subtracted separately, once, inside net monthly value
  (see :func:`net_monthly_value`). See ``CONFIG["hours_saved_basis"]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# The one config dict. Tuning the tool is a single edit, here.
# ---------------------------------------------------------------------------
#
# Threshold comparisons are stated explicitly so there is no ambiguity about
# which side of a boundary is Green/Yellow/Red:
#
#   adoption rate:              >= 0.80 Green,  >= 0.50 Yellow,            else Red
#   success rate:               >= 0.90 Green,  >= 0.70 Yellow,            else Red
#   cost per successful outcome: <= target Green, <= 1.20 x target Yellow, else Red
#
# These are STARTING DEFAULTS that the pilot owner tunes. They are NOT industry
# standards or benchmarks — ValueGap invents no numbers.
CONFIG = {
    # All month fields use YYYY-MM so months sort and join as plain strings.
    "month_format": "YYYY-MM",

    # hours_saved is gross; rework is subtracted only in the net-value formula.
    "hours_saved_basis": "gross",

    # Adoption leak thresholds (fraction of eligible users who are active).
    "adoption": {
        "green_at_or_above": 0.80,
        "yellow_at_or_above": 0.50,
        # below yellow_at_or_above -> Red
    },

    # Quality leak thresholds (success rate = successful / total outcomes).
    # When the pilot sets promised_success_rate (> 0), that promise is the
    # Green line instead of the default below: Green means "met the promise".
    "success": {
        "green_at_or_above": 0.90,
        "yellow_at_or_above": 0.70,
        # below yellow_at_or_above -> Red
        "green_from_pilot_promise": True,
    },

    # Cost leak thresholds, expressed as a multiple of the per-outcome target.
    "cost": {
        "green_at_or_below_mult": 1.00,   # <= 1.00 x target  -> Green
        "yellow_at_or_below_mult": 1.20,  # <= 1.20 x target  -> Yellow
        # above 1.20 x target -> Red
    },

    # Leaks are scored on the trailing window of the most recent N months,
    # so the summary reports where value is leaking NOW. A 1-month window is
    # the latest month; pilot-to-date figures are still shown as context.
    "leak_window_months": 1,
}

# Payback states. "reached_then_lost" = cumulative net value crossed zero but
# has since fallen back below it.
PAYBACK_REACHED = "reached"
PAYBACK_LOST = "reached_then_lost"
PAYBACK_NOT_REACHED = "not_reached"

# Sentinel used in summaries when a rate is undefined (zero denominator).
NA_LABEL = "n/a"


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------
@dataclass
class Pilot:
    """A pilot, defined once.

    ``promised_successful_outcomes`` and ``promised_ai_cost_budget`` together
    give the per-outcome cost target used by the cost leak:
    target = budget / promised successful outcomes (guarded).
    """

    name: str
    start_month: str  # YYYY-MM
    implementation_cost: float  # one-time, dollars
    value_per_hour: float  # user-entered assumption, dollars (labeled as such)
    promised_hours_saved: float  # per month
    promised_successful_outcomes: float  # per month
    promised_success_rate: float  # per month, fraction (e.g. 0.90)
    promised_ai_cost_budget: float  # per month, dollars

    @classmethod
    def from_dict(cls, d: dict) -> "Pilot":
        return cls(
            name=d["name"],
            start_month=d["start_month"],
            implementation_cost=float(d["implementation_cost"]),
            value_per_hour=float(d["value_per_hour"]),
            promised_hours_saved=float(d["promised_hours_saved"]),
            promised_successful_outcomes=float(d["promised_successful_outcomes"]),
            promised_success_rate=float(d["promised_success_rate"]),
            promised_ai_cost_budget=float(d["promised_ai_cost_budget"]),
        )

    @property
    def target_cost_per_outcome(self) -> Optional[float]:
        """Per-outcome cost target the cost leak compares against.

        Derived once from the promised budget and promised successful outcomes
        so there is a single source of truth. ``None`` if no outcomes were
        promised (nothing to divide by)."""
        return cost_per_successful_outcome(
            self.promised_ai_cost_budget, self.promised_successful_outcomes
        )


@dataclass
class MonthlyActual:
    """One CSV row of verified actuals for a month."""

    month: str  # YYYY-MM
    hours_saved: float  # gross, as verified by the pilot owner
    successful_outcomes: float
    total_outcomes: float
    ai_cost: float
    rework_hours: float
    active_users: float
    eligible_users: float

    @classmethod
    def from_row(cls, row: dict) -> "MonthlyActual":
        return cls(
            month=str(row["month"]).strip(),
            hours_saved=float(row["hours_saved"]),
            successful_outcomes=float(row["successful_outcomes"]),
            total_outcomes=float(row["total_outcomes"]),
            ai_cost=float(row["ai_cost"]),
            rework_hours=float(row["rework_hours"]),
            active_users=float(row["active_users"]),
            eligible_users=float(row["eligible_users"]),
        )


# ---------------------------------------------------------------------------
# Formulas — each guards its denominator and returns None when undefined.
# ---------------------------------------------------------------------------
def realization_rate(
    realized_hours: float, promised_hours: float
) -> Optional[float]:
    """realized hours saved / promised hours saved, as a fraction.

    ``None`` if no hours were promised (nothing to realize against)."""
    if promised_hours == 0:
        return None
    return realized_hours / promised_hours


def success_rate(
    successful_outcomes: float, total_outcomes: float
) -> Optional[float]:
    """successful outcomes / total outcomes, as a fraction.

    ``None`` if there were no outcomes at all."""
    if total_outcomes == 0:
        return None
    return successful_outcomes / total_outcomes


def adoption_rate(
    active_users: float, eligible_users: float
) -> Optional[float]:
    """active users / eligible users, as a fraction.

    ``None`` if no users were eligible."""
    if eligible_users == 0:
        return None
    return active_users / eligible_users


def cost_per_successful_outcome(
    ai_cost: float, successful_outcomes: float
) -> Optional[float]:
    """AI cost / successful outcomes (not per token, not per attempt).

    ``None`` if there were zero successful outcomes — the most important guard,
    because "dollars per nothing" is undefined, not infinite."""
    if successful_outcomes == 0:
        return None
    return ai_cost / successful_outcomes


def net_monthly_value(
    hours_saved: float,
    value_per_hour: float,
    ai_cost: float,
    rework_hours: float,
) -> float:
    """(hours_saved x value_per_hour) - ai_cost - (rework_hours x value_per_hour).

    hours_saved is gross; rework is subtracted exactly once, here."""
    return (
        (hours_saved * value_per_hour)
        - ai_cost
        - (rework_hours * value_per_hour)
    )


def cumulative_net_value(
    net_values: list[float], implementation_cost: float
) -> float:
    """sum(net monthly values) - one-time implementation cost."""
    return sum(net_values) - implementation_cost


def payback_month(
    months: list[str], running_cumulative: list[float]
) -> Optional[str]:
    """First month whose cumulative net value is >= 0, else None.

    ``months`` and ``running_cumulative`` are parallel lists in month order.
    ``None`` means "not yet reached"."""
    for month, cum in zip(months, running_cumulative):
        if cum >= 0:
            return month
    return None


def payback_status(running_cumulative: list[float]) -> str:
    """Whether payback was reached, and whether it still holds today."""
    if not any(c >= 0 for c in running_cumulative):
        return PAYBACK_NOT_REACHED
    if running_cumulative[-1] < 0:
        return PAYBACK_LOST
    return PAYBACK_REACHED


# ---------------------------------------------------------------------------
# Analysis — ties the formulas together into one structured result.
# ---------------------------------------------------------------------------
@dataclass
class MonthResult:
    month: str
    realized_hours: float
    promised_hours: float
    realization_rate: Optional[float]
    success_rate: Optional[float]
    adoption_rate: Optional[float]
    cost_per_successful_outcome: Optional[float]
    net_value: float
    cumulative_net_value: float


@dataclass
class Analysis:
    pilot: Pilot
    months: list[MonthResult] = field(default_factory=list)
    # Pilot-to-date totals (the headline figures).
    promised_hours_total: float = 0.0
    realized_hours_total: float = 0.0
    realization_rate_total: Optional[float] = None
    success_rate_total: Optional[float] = None
    adoption_rate_total: Optional[float] = None
    cost_per_outcome_total: Optional[float] = None
    target_cost_per_outcome: Optional[float] = None
    cumulative_net_value: float = 0.0
    implementation_cost: float = 0.0
    payback_month: Optional[str] = None
    payback_status: str = PAYBACK_NOT_REACHED
    # Leak window: the most recent CONFIG["leak_window_months"] months.
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    window_success_rate: Optional[float] = None
    window_adoption_rate: Optional[float] = None
    window_cost_per_outcome: Optional[float] = None
    # Data notes (e.g. missing months) shown alongside the summary.
    warnings: list[str] = field(default_factory=list)


def _window_rates(rows: list[MonthlyActual]):
    """(success, adoption, cost per outcome) pooled over ``rows``."""
    succ = sum(a.successful_outcomes for a in rows)
    return (
        success_rate(succ, sum(a.total_outcomes for a in rows)),
        adoption_rate(
            sum(a.active_users for a in rows), sum(a.eligible_users for a in rows)
        ),
        cost_per_successful_outcome(sum(a.ai_cost for a in rows), succ),
    )


def analyze(pilot: Pilot, actuals: list[MonthlyActual]) -> Analysis:
    """Run every formula over a pilot and its monthly actuals.

    Months are processed in sorted (YYYY-MM) order so cumulative figures and
    the payback month are stable regardless of CSV row order. Raises
    :class:`~valuegap.validation.ValidationError` if a month repeats or falls
    before the pilot's start month."""
    from .validation import check_months  # local import: validation imports this module

    warnings = check_months(pilot, actuals)
    rows = sorted(actuals, key=lambda a: a.month)
    window = rows[-max(1, CONFIG["leak_window_months"]):] if rows else []
    w_success, w_adoption, w_cost = _window_rates(window) if window else (None, None, None)

    months: list[MonthResult] = []
    running = 0.0
    running_cumulative: list[float] = []
    month_labels: list[str] = []

    sum_realized = 0.0
    sum_successful = 0.0
    sum_total_outcomes = 0.0
    sum_active = 0.0
    sum_eligible = 0.0
    sum_ai_cost = 0.0

    for a in rows:
        net = net_monthly_value(
            a.hours_saved, pilot.value_per_hour, a.ai_cost, a.rework_hours
        )
        running += net
        cum = running - pilot.implementation_cost

        months.append(
            MonthResult(
                month=a.month,
                realized_hours=a.hours_saved,
                promised_hours=pilot.promised_hours_saved,
                realization_rate=realization_rate(
                    a.hours_saved, pilot.promised_hours_saved
                ),
                success_rate=success_rate(
                    a.successful_outcomes, a.total_outcomes
                ),
                adoption_rate=adoption_rate(
                    a.active_users, a.eligible_users
                ),
                cost_per_successful_outcome=cost_per_successful_outcome(
                    a.ai_cost, a.successful_outcomes
                ),
                net_value=net,
                cumulative_net_value=cum,
            )
        )

        running_cumulative.append(cum)
        month_labels.append(a.month)

        sum_realized += a.hours_saved
        sum_successful += a.successful_outcomes
        sum_total_outcomes += a.total_outcomes
        sum_active += a.active_users
        sum_eligible += a.eligible_users
        sum_ai_cost += a.ai_cost

    promised_total = pilot.promised_hours_saved * len(rows)

    return Analysis(
        pilot=pilot,
        months=months,
        promised_hours_total=promised_total,
        realized_hours_total=sum_realized,
        realization_rate_total=realization_rate(sum_realized, promised_total),
        success_rate_total=success_rate(sum_successful, sum_total_outcomes),
        adoption_rate_total=adoption_rate(sum_active, sum_eligible),
        cost_per_outcome_total=cost_per_successful_outcome(
            sum_ai_cost, sum_successful
        ),
        target_cost_per_outcome=pilot.target_cost_per_outcome,
        cumulative_net_value=running_cumulative[-1] if running_cumulative else -pilot.implementation_cost,
        implementation_cost=pilot.implementation_cost,
        payback_month=payback_month(month_labels, running_cumulative),
        payback_status=payback_status(running_cumulative),
        window_start=window[0].month if window else None,
        window_end=window[-1].month if window else None,
        window_success_rate=w_success,
        window_adoption_rate=w_adoption,
        window_cost_per_outcome=w_cost,
        warnings=warnings,
    )
