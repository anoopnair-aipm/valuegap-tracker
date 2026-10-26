"""Command-line entry point.

    python -m valuegap.check --pilot data/sample_pilot.json \\
                             --actuals data/sample_monthly.csv

Prints promised vs. realized, realization rate, cost per successful outcome,
cumulative net value, and payback status. Optionally writes the HTML summary,
and with ``--db`` keeps the pilot's monthly history in SQLite so each run can
add just the new month. Runs fully offline; no API key required.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .calculations import analyze
from .narrator import narrate
from .report import build_summary, render_html, render_text
from .storage import connect, load_actuals_csv, load_pilot_json, save_history
from .validation import ValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m valuegap.check",
        description="Report whether an AI pilot delivered the value it promised.",
    )
    parser.add_argument("--pilot", required=True, help="Path to pilot JSON.")
    parser.add_argument("--actuals", required=True, help="Path to monthly actuals CSV.")
    parser.add_argument(
        "--html",
        metavar="PATH",
        help="Also write the HTML executive summary to PATH.",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="Save the pilot and these months to a SQLite history at PATH "
        "and report on the full stored history.",
    )
    parser.add_argument(
        "--narrate",
        action="store_true",
        help="Add a Claude-narrated paragraph if ANTHROPIC_API_KEY is set "
        "(silently skipped otherwise).",
    )
    args = parser.parse_args(argv)

    try:
        pilot = load_pilot_json(args.pilot)
        actuals = load_actuals_csv(args.actuals)
        if args.db:
            actuals = save_history(connect(args.db), pilot, actuals)
        analysis = analyze(pilot, actuals)
    except ValidationError as e:
        print("error: the input has problems:", file=sys.stderr)
        for p in e.problems:
            print(f"  - {p}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: {e.strerror}: {e.filename}", file=sys.stderr)
        return 2

    summary = build_summary(analysis)
    prose = narrate(summary) if args.narrate else None

    if prose:
        print(prose + "\n")
    print(render_text(summary))

    if args.html:
        out = Path(args.html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_html(summary, narrated_prose=prose), encoding="utf-8")
        print(f"\nHTML summary written to {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
