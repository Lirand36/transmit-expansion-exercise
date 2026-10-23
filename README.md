# Q1 2027 expansion plan

GTM Engineer take-home exercise, Transmit Security.

**The answer:** two plays to act on now, two to validate first, and one revenue risk to protect. Each has named accounts, an owner, a next action, and a $ figure that says what it measures.

| Group | Play | Owner | Accounts | $ figure |
| --- | --- | --- | --- | --- |
| Act now | Price to usage | Sales | 19 | $1.6M gap to peer pricing per year |
| Act now | Land and expand | Customer Success | 12 | landed in the last 12 months, not expanded yet |
| Validate first | Q1 expansion window | Sales + CS | 20 | $2.6M prior contract value, not expansion value |
| Validate first | Recover revenue | RevOps + Finance + CS | 19 | $3.1M usage value at peer pricing |
| Protect | Paid, but no usage | Salesforce Architect | 19 | $7.5M paid so far, at risk at renewal |

The figures measure different things, so they are never added up, and none is a forecast. For scale, expansion booked $223k to $391k a quarter.

## Open it (no install)

Open these files in any browser:

| File | What it is |
| --- | --- |
| `submission/index.html` | **Start here.** Presentation, data model, AI component, data-quality memo, and how I used AI. |
| `demo/index.html` | The Q1 plan: the plays, their accounts, owners and next actions. |

## Run it (Python 3.9 or newer)

On a Mac, double-click `start.command`. It sets up Python the first time, rebuilds everything and opens the submission page. Or in a terminal:

```bash
pip install -r requirements.txt
python run.py
```

`run.py` rebuilds everything from the 4 CSVs in `data/raw/`: data checks, lead matching, account signals, the plays, and both pages. Refresh the browser to see the result. Each run prints what moved since the last run.

**No API key needed.** The AI's answers are saved in `output/ai_cache.json`, so a run reuses them. A key is only needed when new lead names appear: set `GEMINI_API_KEY` first. To run without the AI, set `ai.enabled: false` in `config.yaml`.

## Change an assumption

| What | Where |
| --- | --- |
| Peer price (median or cautious), region and segment | Buttons on the plan page |
| Peer price, months of spend used, the target quarter, currency rates, AI on or off | `config.yaml`, then `python run.py` |

**A change to try live:** set `plays.benchmark: low` in `config.yaml` and run again. Peers are then the cheapest quarter of customers, so price to usage drops from $1.6M to $0.4M and recover revenue from $3.1M to $2.1M. Set it back to `median` to return to the plan.

## Why plays, not a predictive score

`python backtest.py` rebuilds an account score at each month end from Jul 2025 to Feb 2026, using only what was known on that date, and checks who created an expansion deal in the next 90 days. Result: AUC 0.60, where 0.5 is a coin flip, on only 15 accounts that expanded. Leads alone score 0.52, so they are shown as a note, not scored. That is too weak to forecast from, so the plan is built on plays the data supports directly, and Q1 is the test. Details per account are in `output/backtest.csv`.

## If the run stops

When the AI is unsure about a lead, the run stops before building a new plan. Open `data/review_queue.csv`, set `status` to `decided` and fill `decided_account_id` (leave it blank for "not a customer"), `decided_by` and `decided_on`. Then run again. Each decision is saved and reused.

## What's where

```
config.yaml         every assumption, in one place
run.py              runs the whole pipeline
backtest.py         tests the ranking against past expansion deals
src/                clean, check, match (code + AI), signals, score, plays, export
data/raw/           the 4 CSVs as received
data/lead_labels.csv    answer list used to measure the AI
data/review_queue.csv   leads waiting for, or decided by, a person
output/             results of the last run (checks, matches, plays)
logs/               every change made to the data, step by step
demo/               the plan page
submission/         the submission page
```
