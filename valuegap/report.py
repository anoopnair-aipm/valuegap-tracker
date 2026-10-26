"""Executive summary generation.

The RULE-BASED summary here is the PRIMARY output. It is complete and correct
with no API key set: all headline numbers plus the top 3 leaks, each with one
fix, in plain executive language. :mod:`valuegap.narrator` can optionally
smooth the prose, but this module alone is enough to clone and run.

Nothing here invents a number — every figure shown comes straight from the
:class:`~valuegap.calculations.Analysis`.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Optional

from .calculations import PAYBACK_LOST, PAYBACK_REACHED, Analysis
from .leaks import NA, Leak, evaluate_leaks, window_label


# ---------------------------------------------------------------------------
# Formatting helpers — every one renders None as a clear label, never a crash.
# ---------------------------------------------------------------------------
def fmt_pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}"


def fmt_money2(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"${x:,.2f}"


def fmt_hours(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:,.0f}"


# ---------------------------------------------------------------------------
# Deterministic summary model
# ---------------------------------------------------------------------------
@dataclass
class Summary:
    pilot_name: str
    promised_hours: float
    realized_hours: float
    realization_rate: Optional[float]
    cost_per_outcome: Optional[float]
    target_cost_per_outcome: Optional[float]
    cumulative_net_value: float
    implementation_cost: float
    payback_month: Optional[str]
    leaks: list[Leak]
    value_per_hour: float
    payback_status: str = ""
    leak_window: str = "n/a"  # the month(s) the leaks are scored on
    warnings: list[str] = field(default_factory=list)  # data notes, e.g. missing months


def build_summary(analysis: Analysis) -> Summary:
    return Summary(
        pilot_name=analysis.pilot.name,
        promised_hours=analysis.promised_hours_total,
        realized_hours=analysis.realized_hours_total,
        realization_rate=analysis.realization_rate_total,
        cost_per_outcome=analysis.cost_per_outcome_total,
        target_cost_per_outcome=analysis.target_cost_per_outcome,
        cumulative_net_value=analysis.cumulative_net_value,
        implementation_cost=analysis.implementation_cost,
        payback_month=analysis.payback_month,
        leaks=evaluate_leaks(analysis),
        value_per_hour=analysis.pilot.value_per_hour,
        payback_status=analysis.payback_status,
        leak_window=window_label(analysis) if analysis.months else "n/a",
        warnings=list(analysis.warnings),
    )


def payback_phrase(summary: Summary) -> str:
    if summary.payback_status == PAYBACK_LOST:
        return (
            f"reached in {summary.payback_month}, but cumulative net value has "
            "since fallen back below zero"
        )
    if summary.payback_status == PAYBACK_REACHED:
        return f"paid back in {summary.payback_month}"
    return "not yet reached"


def leak_headline(summary: Summary) -> str:
    """One line on where value is leaking now."""
    active = [lk for lk in summary.leaks if lk.is_active]
    if active:
        worst = active[0]
        return f"Biggest leak now: {worst.kind.title()} ({worst.status})."
    if all(lk.status == NA for lk in summary.leaks):
        return "Leaks cannot be scored yet: the latest data has nothing to measure."
    return f"No active leaks as of {summary.leak_window}: every scored check is Green."


# ---------------------------------------------------------------------------
# Plain-text executive summary (the deterministic, no-API primary output).
# ---------------------------------------------------------------------------
def render_text(summary: Summary) -> str:
    lines: list[str] = []
    lines.append(f"ValueGap executive summary — {summary.pilot_name}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(
        f"Promised vs. realized hours: {fmt_hours(summary.realized_hours)} "
        f"realized against {fmt_hours(summary.promised_hours)} promised "
        f"({fmt_pct(summary.realization_rate)} of the promise)."
    )
    lines.append(
        f"Cost per successful outcome: {fmt_money2(summary.cost_per_outcome)} "
        f"(target {fmt_money2(summary.target_cost_per_outcome)})."
    )
    lines.append(
        f"Cumulative net value: {fmt_money(summary.cumulative_net_value)} "
        f"after a {fmt_money(summary.implementation_cost)} one-time build cost."
    )
    lines.append(f"Payback: {payback_phrase(summary)}.")
    lines.append("")
    lines.append(f"Value leaks as of {summary.leak_window} (worst first):")
    lines.append(leak_headline(summary))
    for i, leak in enumerate(summary.leaks, 1):
        lines.append(f"  {i}. [{leak.status}] {leak.message}")
        if leak.trend:
            lines.append(f"     Trend: {leak.trend}")
        lines.append(f"     Fix: {leak.fix}")
    lines.append("")
    if summary.warnings:
        lines.append("Data notes:")
        lines.extend(f"  - {w}" for w in summary.warnings)
        lines.append("")
    lines.append(
        "Note: thresholds and the value-per-hour figure "
        f"({fmt_money2(summary.value_per_hour)}/hour) are user-entered starting "
        "defaults, not benchmarks. The sample pilot is illustrative only."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML executive summary
# ---------------------------------------------------------------------------
_STATUS_COLOR = {
    "Red": "#c0392b",
    "Yellow": "#b7950b",
    "Green": "#1e8449",
    "n/a": "#707070",
}


def render_html(summary: Summary, narrated_prose: Optional[str] = None) -> str:
    """Render the one-page HTML executive summary.

    ``narrated_prose`` is the optional polished paragraph from the narrator.
    When present it is shown as an opening paragraph ABOVE the deterministic
    figures; the figures and leak table are always shown verbatim so the
    numbers are never hidden behind prose."""
    e = html.escape

    narrated_block = ""
    if narrated_prose:
        narrated_block = (
            '<div class="narrated">'
            '<div class="narrated-label">Executive narration</div>'
            f"<p>{e(narrated_prose).replace(chr(10), '<br>')}</p>"
            "</div>"
        )

    leak_rows = []
    for i, leak in enumerate(summary.leaks, 1):
        color = _STATUS_COLOR.get(leak.status, "#707070")
        leak_rows.append(
            f"""
            <div class="leak">
              <div class="leak-head">
                <span class="rank">{i}</span>
                <span class="badge" style="background:{color}">{e(leak.status)}</span>
                <span class="leak-kind">{e(leak.kind.title())} leak</span>
              </div>
              <p class="leak-msg">{e(leak.message)}</p>
              {f'<p class="leak-trend">Trend: {e(leak.trend)}</p>' if leak.trend else ''}
              <p class="leak-fix"><strong>Fix:</strong> {e(leak.fix)}</p>
            </div>
            """
        )

    cum_color = "#1e8449" if summary.cumulative_net_value >= 0 else "#c0392b"

    if summary.payback_status == PAYBACK_LOST:
        payback_value = f"{e(summary.payback_month)}, since lost"
        payback_note = "cumulative is back below $0"
    elif summary.payback_status == PAYBACK_REACHED:
        payback_value = e(summary.payback_month)
        payback_note = "first month cumulative &ge; $0"
    else:
        payback_value = "not yet"
        payback_note = "cumulative still below $0"

    notes_block = ""
    if summary.warnings:
        items = "".join(f"<li>{e(w)}</li>" for w in summary.warnings)
        notes_block = f'<div class="notes"><strong>Data notes</strong><ul>{items}</ul></div>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ValueGap summary — {e(summary.pilot_name)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    max-width: 760px; margin: 2rem auto; padding: 0 1rem;
    color: #1a1a1a; background: #ffffff; line-height: 1.5;
  }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  .sub {{ color: #666; margin-top: 0; font-size: 0.95rem; }}
  .narrated {{
    background: #f4f7fb; border: 1px solid #d6e0ee; border-radius: 10px;
    padding: 1rem 1.2rem; margin: 1.2rem 0;
  }}
  .narrated-label {{
    font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase;
    color: #567; margin-bottom: 0.4rem;
  }}
  .narrated p {{ margin: 0; }}
  .grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.8rem; margin: 1.2rem 0;
  }}
  .card {{
    border: 1px solid #e3e3e3; border-radius: 10px; padding: 0.9rem 1rem;
    background: #fafafa;
  }}
  .card .label {{ font-size: 0.75rem; color: #777; text-transform: uppercase; letter-spacing: 0.04em; }}
  .card .value {{ font-size: 1.35rem; font-weight: 650; margin-top: 0.25rem; }}
  .card .note {{ font-size: 0.78rem; color: #888; margin-top: 0.2rem; }}
  .leak {{ border-left: 4px solid #ddd; padding: 0.4rem 0 0.4rem 1rem; margin: 1rem 0; }}
  .leak-head {{ display: flex; align-items: center; gap: 0.5rem; }}
  .rank {{
    display: inline-flex; width: 1.5rem; height: 1.5rem; border-radius: 50%;
    background: #333; color: #fff; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 700;
  }}
  .badge {{ color: #fff; font-size: 0.72rem; font-weight: 700; padding: 0.1rem 0.5rem; border-radius: 4px; text-transform: uppercase; }}
  .leak-kind {{ font-weight: 600; }}
  .leak-msg {{ margin: 0.4rem 0 0.2rem; }}
  .leak-fix {{ margin: 0.2rem 0; color: #333; }}
  .leak-trend {{ margin: 0.2rem 0; color: #666; font-size: 0.88rem; }}
  .headline {{ font-weight: 600; margin: 0.2rem 0 0.6rem; }}
  .notes {{ background: #fff8e6; border: 1px solid #f0dca8; border-radius: 8px; padding: 0.7rem 1rem; margin: 1rem 0; font-size: 0.9rem; }}
  .notes ul {{ margin: 0.3rem 0 0; padding-left: 1.2rem; }}
  .disclaimer {{ font-size: 0.78rem; color: #888; border-top: 1px solid #eee; margin-top: 2rem; padding-top: 1rem; }}
</style>
</head>
<body>
  <h1>ValueGap executive summary</h1>
  <p class="sub">{e(summary.pilot_name)} &middot; promised vs. realized</p>

  {narrated_block}

  <div class="grid">
    <div class="card">
      <div class="label">Realization rate</div>
      <div class="value">{fmt_pct(summary.realization_rate)}</div>
      <div class="note">{fmt_hours(summary.realized_hours)} of {fmt_hours(summary.promised_hours)} promised hours</div>
    </div>
    <div class="card">
      <div class="label">Cost / successful outcome</div>
      <div class="value">{fmt_money2(summary.cost_per_outcome)}</div>
      <div class="note">target {fmt_money2(summary.target_cost_per_outcome)}</div>
    </div>
    <div class="card">
      <div class="label">Cumulative net value</div>
      <div class="value" style="color:{cum_color}">{fmt_money(summary.cumulative_net_value)}</div>
      <div class="note">after {fmt_money(summary.implementation_cost)} build cost</div>
    </div>
    <div class="card">
      <div class="label">Payback</div>
      <div class="value">{payback_value}</div>
      <div class="note">{payback_note}</div>
    </div>
  </div>

  <h2 style="font-size:1.1rem;">Value leaks as of {e(summary.leak_window)}</h2>
  <p class="headline">{e(leak_headline(summary))}</p>
  {''.join(leak_rows)}
  {notes_block}

  <p class="disclaimer">
    Thresholds and the value-per-hour figure ({fmt_money2(summary.value_per_hour)}/hour)
    are user-entered starting defaults, not industry benchmarks. ValueGap invents
    no numbers; every figure above is calculated from the actuals you entered.
    The sample pilot shipped with this repo is illustrative only and is not a
    claim about any real pilot.
  </p>
</body>
</html>
"""
