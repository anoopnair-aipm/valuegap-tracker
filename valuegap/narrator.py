"""Optional Claude-as-narrator polish layer.

Contract (numbers in, prose out — and Claude never writes a number):

* The rule-based summary from :mod:`valuegap.report` is the primary output and
  is always complete on its own. Its figures are always shown verbatim next
  to any narration.
* :func:`narrate` gives Claude the calculated figures as NAMED PLACEHOLDERS
  (``{realization_rate}``, ``{cost_per_outcome}``, ...) with their values for
  context, and asks for prose that refers to figures only through those
  placeholders. ValueGap then substitutes the values itself.
* The template Claude returns is rejected — and narration is skipped — if it
  contains any digit or spelled-out quantity, uses an unknown placeholder, or
  leaves out a required one. So Claude cannot change, round, swap, or invent a
  number: every number in the narration was put there by code.
* A missing key, missing package, refusal, API error, or rejected template all
  return ``None``: callers show the rule-based text alone. The tool never
  breaks because the narrator was unavailable.

The model defaults to ``claude-opus-5-5`` at low effort (a plain rewrite) and
can be overridden with ``VALUEGAP_NARRATOR_MODEL``.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from .report import Summary, fmt_hours, fmt_money, fmt_money2, fmt_pct, leak_headline, payback_phrase

DEFAULT_MODEL = "claude-opus-5-5"
# Models that accept the server-side refusal fallback ("default" form).
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

_PLACEHOLDER_RE = re.compile(r"\{([a-z0-9_]+)\}")
_DIGIT_RE = re.compile(r"\d")
# Spelled-out quantities would bypass the digit check. "one" is allowed
# ("one fix") — it states no figure.
_NUMBER_WORD_RE = re.compile(
    r"\b(zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"million|billion|percent|dozen|half|double|triple|twice|thrice)\b",
    re.IGNORECASE,
)

# The figures a narration must mention.
REQUIRED = ("realization_rate", "cost_per_outcome", "cumulative_net_value", "payback")

_SYSTEM_PROMPT = (
    "You narrate an executive summary for an AI-pilot value tracker. You get "
    "named facts as {placeholder} = value. Write one short paragraph of plain "
    "executive prose a busy leader can read in thirty seconds, covering "
    "promised vs. realized hours, cost per successful outcome, cumulative net "
    "value, payback, and where value is leaking now with its fix.\n\n"
    "Refer to every figure ONLY by its placeholder, written exactly as given, "
    "e.g. {realization_rate}. Never write a digit, a number word, or a "
    "percentage yourself; the placeholders are filled in afterwards. You must "
    "use {realization_rate}, {cost_per_outcome}, {cumulative_net_value} and "
    "{payback}. Do not add any statistic, benchmark, or company name, and do "
    "not draw conclusions the facts do not state. Return the paragraph only, "
    "with no heading or list."
)


def facts_from_summary(summary: Summary) -> dict[str, str]:
    """Every figure the narration may use, already formatted by code."""
    facts = {
        "pilot_name": summary.pilot_name,
        "realized_hours": fmt_hours(summary.realized_hours),
        "promised_hours": fmt_hours(summary.promised_hours),
        "realization_rate": fmt_pct(summary.realization_rate),
        "cost_per_outcome": fmt_money2(summary.cost_per_outcome),
        "target_cost_per_outcome": fmt_money2(summary.target_cost_per_outcome),
        "cumulative_net_value": fmt_money(summary.cumulative_net_value),
        "implementation_cost": fmt_money(summary.implementation_cost),
        "payback": payback_phrase(summary),
        "leak_window": summary.leak_window,
        "leak_headline": leak_headline(summary),
    }
    for i, leak in enumerate(summary.leaks, 1):
        facts[f"leak{i}_kind"] = leak.kind
        facts[f"leak{i}_status"] = leak.status
        facts[f"leak{i}_detail"] = leak.message
        facts[f"leak{i}_fix"] = leak.fix
        if leak.trend:
            facts[f"leak{i}_trend"] = leak.trend
    return facts


def check_template(template: str, facts: dict[str, str]) -> Optional[str]:
    """Return why ``template`` is unsafe to fill, or ``None`` if it is safe."""
    used = set(_PLACEHOLDER_RE.findall(template))
    unknown = used - facts.keys()
    if unknown:
        return f"unknown placeholder(s): {', '.join(sorted(unknown))}"
    missing = [p for p in REQUIRED if p not in used]
    if missing:
        return f"missing required placeholder(s): {', '.join(missing)}"
    bare = _PLACEHOLDER_RE.sub("", template)
    if _DIGIT_RE.search(bare):
        return "contains a number outside the placeholders"
    word = _NUMBER_WORD_RE.search(bare)
    if word:
        return f"contains a spelled-out quantity ('{word.group(0)}')"
    return None


def fill_template(template: str, facts: dict[str, str]) -> str:
    """Substitute placeholders with their code-formatted values."""
    return _PLACEHOLDER_RE.sub(lambda m: facts[m.group(1)], template)


def _request_template(facts: dict[str, str], model: str) -> Optional[str]:
    """Ask Claude for a placeholder template. ``None`` on any problem."""
    try:
        import anthropic  # imported lazily so the tool runs without it installed
    except Exception:
        return None

    listing = "\n".join(f"{{{k}}} = {v}" for k, v in facts.items())
    params = dict(
        model=model,
        max_tokens=16000,
        system=_SYSTEM_PROMPT,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": "Facts:\n" + listing}],
    )
    try:
        client = anthropic.Anthropic()
        if model in _FALLBACK_MODELS:
            # On a policy decline the API re-runs the request on a fallback model.
            resp = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
            )
        else:
            resp = client.messages.create(**params)
    except Exception:
        return None  # any auth / network / API error -> silent fallback

    if getattr(resp, "stop_reason", None) == "refusal":
        return None
    text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    return text or None


def narrate(summary: Summary, *, model: Optional[str] = None) -> Optional[str]:
    """Return narrated prose for ``summary``, or ``None`` to use the rules alone.

    Never raises. Every number in the result was inserted by code."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    model = model or os.environ.get("VALUEGAP_NARRATOR_MODEL") or DEFAULT_MODEL
    facts = facts_from_summary(summary)
    template = _request_template(facts, model)
    if template is None or check_template(template, facts) is not None:
        return None
    return fill_template(template, facts)
