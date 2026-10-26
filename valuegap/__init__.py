"""ValueGap Tracker — does an AI pilot deliver the value it promised?

Adoption is not value. This package turns one pilot's monthly actuals into a
promised-vs-realized story, flags where value leaks, and writes a plain-language
executive summary. It invents no numbers.
"""

from .calculations import (
    CONFIG,
    Analysis,
    MonthlyActual,
    Pilot,
    analyze,
)
from .leaks import Leak, evaluate_leaks
from .report import build_summary, render_html, render_text

__version__ = "0.1.0"

__all__ = [
    "CONFIG",
    "Analysis",
    "MonthlyActual",
    "Pilot",
    "analyze",
    "Leak",
    "evaluate_leaks",
    "build_summary",
    "render_html",
    "render_text",
]
