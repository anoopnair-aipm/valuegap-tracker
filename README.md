# ValueGap Tracker

**Adoption is not value.** An AI pilot can be live, used every day, and still
not pay back. ValueGap Tracker makes that gap visible — it tracks whether a
pilot delivered the value it *promised*, month by month, in plain executive
language, instead of leaving it to a slide deck.

**Try the live demo: https://valuegap-tracker.streamlit.app** (sample data,
illustrative only; anything you enter stays in your own browser session).

You define one pilot once, add one row of actuals per month, and the tool tells
you: how much of the promise was realized, what each successful outcome costs,
whether the pilot has paid back its build cost yet, and *where the value is
leaking* — with one concrete fix for each leak.

This is the fourth piece of a four-repo story:

| Repo | What it proves |
| --- | --- |
| `frugal-claude` | you can **control** AI cost |
| `local-rag-system` | you can **build** AI |
| `ProdGate AI` | you know what it takes to **ship** AI safely |
| **`valuegap-tracker`** | you can **prove whether it delivered value** after launch |

---

## The promised-vs-realized story (one page)

A pilot is sold on a promise: *"it will save ~200 hours a month."* ValueGap
holds the actuals against that promise every month and reduces the result to
five numbers a leader can read in thirty seconds:

- **Realization rate** — realized hours ÷ promised hours.
- **Cost per successful outcome** — AI cost ÷ successful outcomes (not per
  token, not per attempt).
- **Cumulative net value** — value of hours saved, minus AI cost, minus rework,
  minus the one-time build cost.
- **Payback** — the first month cumulative net value crosses zero, or "not yet"
  (and it says so if payback was reached and later lost).
- **Value leaks now** — adoption, quality, cost — scored on the latest month,
  ranked worst-first, each with one fix and a trend from month 1.

### The demo arc (the shipped sample)

The sample pilot, **"Drafting assistant"**, is built to tell the story
hiring managers remember:

- **Month 1** starts *below promise* — only 36% of eligible users are active, so
  most of the promised hours can't be saved. Adoption is the biggest leak.
- Over the next months adoption climbs as the leak is addressed; realized hours
  rise toward the promise.
- **By month 4** cumulative net value crosses zero — the pilot has paid back its
  $20,000 build cost. Realization reaches ~83% of promise over the six months,
  with quality and cost both healthy. Adoption was the whole story, and the leak
  check shows it: `Red (36%) in 2026-01 -> Green (92%) in 2026-06`.

> The sample pilot is **illustrative only**. Its numbers are not a claim about
> any real pilot.

---

## How to use it, step by step

### Step 1: Open the app

Pick one:

- **No install:** open the live demo at **https://valuegap-tracker.streamlit.app**.
  Anything you enter there stays in your own browser session and is gone when
  you close the tab, so use it to try the tool, not to keep real records.
- **On your own computer** (keeps your history between sessions). You need
  Python 3.10 or newer:

  ```bash
  git clone https://github.com/anoopnair-aipm/valuegap-tracker.git
  cd valuegap-tracker
  python3 -m venv .venv
  source .venv/bin/activate        # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  streamlit run app.py
  ```

  Your browser opens the dashboard at `http://localhost:8501`. Next time, you
  only need the `cd`, `source`, and `streamlit run app.py` lines.

### Step 2: Explore the sample

The app opens with **"Use the shipped sample pilot"** switched on. It loads an
illustrative pilot, "Drafting assistant", with six months of made-up data.
Scroll to **3. Dashboard** to see what a finished report looks like: 83%
realization, $2.12 per successful outcome, $32,460 net value, payback in
2026-04, and adoption turning from Red to Green.

### Step 3: Define your pilot (once)

Switch the sample **off**, leave **Pilot** on "New pilot", and fill in what was
promised. (A red "name is missing" note shows until you type a pilot name;
that's expected.)

| Field | What to enter |
| --- | --- |
| Pilot name | A generic name, e.g. "Support reply assistant" |
| Start month | The first month of the pilot, as `YYYY-MM` |
| One-time implementation cost ($) | What it cost to build and launch |
| Value per hour saved ($) | Your assumption for what an hour of saved time is worth |
| Promised hours saved / month | The time savings the pilot was approved on |
| Promised successful outcomes / month | How many good results it should produce |
| Promised success rate (0–1) | The quality bar, e.g. `0.90`; this becomes the quality leak's Green line |
| Promised AI cost budget / month ($) | Expected monthly AI spend |

Click **Save pilot**. The app shows the cost-per-outcome target it derives
(budget ÷ promised successful outcomes).

### Step 4: Prepare a monthly CSV

In Excel or Google Sheets, make one row per month with exactly these column
headers, then save it as CSV (Excel: *File → Save As → CSV UTF-8*; Google
Sheets: *File → Download → .csv*):

| Column | Meaning |
| --- | --- |
| `month` | The month, as `YYYY-MM` |
| `hours_saved` | Hours saved that month, as verified by the pilot owner (before rework) |
| `successful_outcomes` | Outcomes that met the quality bar |
| `total_outcomes` | All outcomes attempted |
| `ai_cost` | AI spend that month, in dollars |
| `rework_hours` | Hours spent fixing the AI's output |
| `active_users` | People who actually used it that month |
| `eligible_users` | People who could have used it |

Example (the first sample month):

```csv
month,hours_saved,successful_outcomes,total_outcomes,ai_cost,rework_hours,active_users,eligible_users
2026-01,80,175,190,500,15,18,50
```

### Step 5: Import it

In **2. Import monthly actuals**, upload the CSV and click **Import**. If the
file has a problem (a blank cell, more successes than outcomes, a month before
the pilot started, a month listed twice), nothing is imported and the app lists
each problem by row, so you can fix the file and try again.

### Step 6: Read the dashboard

| You see | What it tells you |
| --- | --- |
| **Realization rate** | How much of the promised hours were actually saved |
| **Cost / successful outcome** | What each good result cost, against your target |
| **Cumulative net value** | Value of hours saved, minus AI cost, rework, and build cost, so far |
| **Payback** | The month the pilot paid back its build cost, "not yet", or reached-then-lost |
| **Charts and monthly table** | Promised vs. realized hours and net value, month by month |
| **Value leaks** | Adoption, quality, and cost, scored on the latest month, worst first, each with one fix and its trend since month 1 |
| **Executive summary** | The same story in plain language; any missing months are listed as data notes |

### Step 7: Add each new month

Next month, choose your pilot in the **Pilot** list, upload a CSV with just the
new month's row, and click **Import**. The dashboard updates using the whole
history. Re-importing a month replaces it, so you can correct earlier numbers.

### Step 8: Share the result

Click **Download HTML executive summary** for a one-page report you can email
or attach to a steering-committee deck.

### Prefer the command line?

Everything above also works offline, with no API key, from the terminal:

```bash
python -m valuegap.check --pilot data/sample_pilot.json --actuals data/sample_monthly.csv
```

Add `--html reports/summary.html` to also write the HTML summary, and
`--db valuegap.db` to keep the pilot's history so each later run only needs that
month's CSV row. Use [`data/sample_pilot.json`](data/sample_pilot.json) as the
template for your own pilot file.

### Input checks

Bad input stops with a row-level message, never a traceback or a silently wrong
number: blank or non-numeric cells, `nan`/`inf`, negative values, more
successes than outcomes, more active than eligible users, months not in
`YYYY-MM`, a month listed twice, or a month before the pilot's start. Friendly
formats are accepted: `$1,200`, header case and spacing, Excel's UTF-8 CSV
export, and `2026-9` (read as `2026-09`). Missing months are flagged as a data
note in the summary.

---

## Tech stack

Deliberately small: the engine is plain Python, and every dependency has one job.

| Layer | Technology | What it does here |
| --- | --- | --- |
| Language | **Python 3.10+** | Everything. The live demo runs on 3.12. |
| Dashboard | **[Streamlit](https://streamlit.io)** | The web UI: pilot form, CSV upload, metrics, charts, monthly table, HTML download |
| Calculation engine | Python standard library | Every formula, leak rule, and threshold, in [`valuegap/calculations.py`](valuegap/calculations.py) and [`valuegap/leaks.py`](valuegap/leaks.py) |
| Input validation | Python standard library (`csv`, `json`, `re`) | Row-level checks on the pilot definition and monthly CSV ([`valuegap/validation.py`](valuegap/validation.py)) |
| Storage | **SQLite** (`sqlite3`, built into Python) | Keeps each pilot and its monthly history on your machine (`valuegap.db`). On the public demo, history lives in memory, per browser session. |
| Reports | Python standard library (`html`) | The plain-text and one-page HTML executive summaries ([`valuegap/report.py`](valuegap/report.py)) |
| Command line | Python standard library (`argparse`) | `python -m valuegap.check` for scripted, offline runs |
| Optional narration | **[Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)** + Claude (`claude-opus-5-5`) | Turns the finished summary into one paragraph of prose. Never writes a number; off unless you set an API key. |
| Tests | **pytest** + Streamlit's `AppTest` | 97 tests, including the dashboard run headlessly |
| Hosting | **[Streamlit Community Cloud](https://streamlit.io/cloud)** | Serves the live demo straight from this repo's `main` branch |

Nothing leaves your machine unless you turn on the optional narrator, which
sends the finished summary (the pilot name, calculated figures, and leak
checks, never your raw CSV) to the Claude API.

---

## How the numbers are made

All formulas and **every threshold live in one config dict** in
[`valuegap/calculations.py`](valuegap/calculations.py), so re-tuning the tool is
a single edit:

| Metric | Formula |
| --- | --- |
| Realization rate | realized hours ÷ promised hours |
| Success rate | successful outcomes ÷ total outcomes |
| Adoption rate | active users ÷ eligible users |
| Cost per successful outcome | AI cost ÷ successful outcomes |
| Net monthly value | (hours × value/hour) − AI cost − (rework hours × value/hour) |
| Cumulative net value | Σ net monthly value − one-time implementation cost |
| Payback month | first month cumulative net value ≥ 0, else "not yet reached" |

**`hours_saved` is gross.** Rework is *not* pre-subtracted from it; rework is
subtracted exactly once, inside the net-value formula, as the formula above
shows (`hours_saved_basis: "gross"` in the config).

### Leak thresholds (starting defaults — not benchmarks)

These are **user-entered starting defaults** the pilot owner tunes, labeled as
such. They are not industry standards, and ValueGap invents no numbers.

| Leak | Green | Yellow | Red |
| --- | --- | --- | --- |
| Adoption | `>= 0.80` | `>= 0.50` | below 0.50 |
| Quality (success rate) | `>=` promised rate (default `0.90`) | `>= 0.70` | below 0.70 |
| Cost / outcome | `<=` target | `<= 1.20 ×` target | above 1.20 × target |

The quality Green line is the pilot's own **promised success rate** when one is
set, so Green means "met the promise". The cost-per-outcome **target** is
derived once from the promised AI budget ÷ promised successful outcomes.

Leaks are scored on the **latest month** (`leak_window_months: 1` in the
config; raise it to score a trailing window), so a leak that has been fixed
reads as fixed instead of being dragged down by early months. Each check shows
its trend from the first month.

### Every denominator is guarded

Realization (promised hours = 0), success rate (total outcomes = 0), adoption
(eligible users = 0), and especially cost per successful outcome (successful
outcomes = 0) never crash and never emit `inf`/`NaN`. They return a clearly
labeled **n/a**, and the summary reads it gracefully. Months use `YYYY-MM`
throughout so they sort and join as plain strings.

---

## The narrator is optional polish, not the engine

The **rule-based executive summary is the primary output**. It is complete and
correct with **no API key set** — all headline numbers plus the top 3 leaks,
each with one fix, in plain language. Clone and run; it just works.

If `ANTHROPIC_API_KEY` is present, [`valuegap/narrator.py`](valuegap/narrator.py)
can add a short narrated paragraph (`--narrate` on the CLI, a button in the
dashboard — one call per set of figures, never on every click). Claude is a
**narrator, not a calculator, and never writes a number**: it gets the figures as
named placeholders (`{realization_rate}`, `{cost_per_outcome}`, ...) and writes
prose that uses only those placeholders; ValueGap fills in the values itself.
Any reply with a digit, a spelled-out quantity, an unknown placeholder, or a
missing headline figure is discarded. On a missing key, missing package,
refusal, or any API error, the rule-based summary is shown alone.

The narrator uses `claude-opus-5-5` at low effort, with the API's server-side
refusal fallback on. Set `VALUEGAP_NARRATOR_MODEL` to use a different model.

---

## Tests

```bash
pytest
```

One test per calculation and per leak check, plus a zero-denominator test for
each rate; input-validation, SQLite history and CLI tests; tests that the
summary is complete with no API key and that the narrator can never put a
number in the prose itself; and headless dashboard tests (`tests/test_app.py`,
skipped when `streamlit` is not installed).

---

## Project layout

```
valuegap-tracker/
├── README.md
├── app.py                  # Streamlit: define pilot -> import CSV -> dashboard
├── valuegap/
│   ├── calculations.py     # all formulas + the one config dict
│   ├── leaks.py            # adoption / quality / cost leak checks
│   ├── validation.py       # input checks for pilot JSON and monthly CSV
│   ├── storage.py          # SQLite: pilots + monthly actuals
│   ├── narrator.py         # optional Claude polish (numbers in, prose out)
│   ├── report.py           # plain-text + HTML executive summary
│   └── check.py            # `python -m valuegap.check` CLI
├── data/
│   ├── sample_pilot.json   # generic sample pilot (illustrative only)
│   └── sample_monthly.csv  # 6 months of generic actuals
├── tests/
└── reports/                # generated HTML summaries (gitignored)
```

---

## Ground rules

- **No invented stats, no benchmark numbers, no named companies, no real data.**
  Every figure in a summary is calculated from the actuals you entered.
- Thresholds and the value-per-hour figure are **user-entered starting
  defaults**, clearly labeled as assumptions.
- The sample pilot is illustrative only.

## License

[MIT](LICENSE).
