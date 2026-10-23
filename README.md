# Q1 2027 expansion plan

GTM Engineer take-home exercise, Transmit Security.

**The answer:** work 19 paying customers for expansion in Q1. At past rates (7.5% of customers open an expansion deal in a quarter) that is 1 to 2 deals, about $64k of new pipeline and $44k of bookings, mostly closing in Q2. Each extra account that opens a deal adds about $45k. Two more tracks run beside it: a contract check on 12 accounts that use the product with no won deal (RevOps with Finance), and a win-back of 7 that lost their renewal (Customer Success).

**The check:** the same math on all 97 paying customers gives $297k a quarter. Expansion actually booked $223k, $391k and $263k in the last three quarters.

## Open it (no install)

Open these files in any browser:

| File | What it is |
| --- | --- |
| `submission/index.html` | **Start here.** Presentation, data model, AI component, data-quality memo, and how I used AI. |
| `demo/index.html` | The Q1 plan. Move a lever and the plan updates instantly. |

## Run it (Python 3.9 or newer)

On a Mac, double-click `start.command`. It sets up Python the first time, rebuilds everything and opens the submission page. Or in a terminal:

```bash
pip install -r requirements.txt
python run.py
```

`run.py` rebuilds everything from the 4 CSVs in `data/raw/`: data checks, lead matching, scoring, the plan, and both pages. Refresh the browser to see the result. Each run prints what moved since the last run.

**No API key needed.** The AI's answers are saved in `output/ai_cache.json`, so a run reuses them. A key is only needed when new lead names appear: set `GEMINI_API_KEY` first. To run without the AI, set `ai.enabled: false` in `config.yaml`.

## Change an assumption

| What | Where |
| --- | --- |
| Accounts the team can work, share that open a deal, deal size, win rate, region and segment | Levers on the plan page |
| How much each signal and each lead source counts, currency conversion on or off | "How we rank" tab on the plan page |
| Currency rates, how far back leads count, how many leads make full intent, months of spend used for headroom, what counts as shrinking use, AI on or off | `config.yaml`, then `python run.py` |

**A deeper change to try:** switch the AI off (`ai.enabled: false` in `config.yaml`) and run again. Leads with messy names are no longer tied to accounts, so Cascade Energy Group and Westbrook Telecom drop out of the Q1 list, Everline Stores and Harbor Logistics come in, and the pipeline moves from $64k to $61k. Set it back to `true` and run again to return to the plan.

## How well does the ranking predict?

`python backtest.py` rebuilds the same signals and score at each month end from Jul 2025 to Feb 2026, using only what was known on that date, and checks who created an expansion deal in the next 90 days. Result: AUC 0.56, where 0.5 is a coin flip. Headroom alone scores 0.64 and depth 0.60; intent (0.52) and momentum (0.47) show no edge. Only 15 accounts expanded in that window, too few to set the weights from data, so the weights are judgment calls and Q1 is the real test. Expansion deals before Jul 2025 can't be tested: usage data starts in Apr 2025. Details per account are in `output/backtest.csv`.

## If the run stops

When the AI is unsure about a lead, the run stops before building a new plan. Open `data/review_queue.csv`, set `status` to `decided` and fill `decided_account_id` (leave it blank for "not a customer"), `decided_by` and `decided_on`. Then run again. Each decision is saved and reused.

## What's where

```
config.yaml         every assumption, in one place
run.py              runs the whole pipeline
backtest.py         tests the ranking against past expansion deals
src/                clean, check, match (code + AI), signals, score, export
data/raw/           the 4 CSVs as received
data/lead_labels.csv    answer list used to measure the AI
data/review_queue.csv   leads waiting for, or decided by, a person
output/             results of the last run (checks, matches, ranking, pipeline)
logs/               every change made to the data, step by step
demo/               the plan page and its scoring engine
submission/         the submission page
```
