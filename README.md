# Q1 2027 expansion plan

GTM Engineer take-home exercise, Transmit Security.

**The answer:** work 24 accounts in Q1 to create about $1.6M of expansion pipeline (range $1.1M to $2.3M), or about $1.1M in expected bookings.

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
| Accounts the team can work, deal size, win rate, accounts with no won deal, region and segment | Levers on the plan page |
| How much each signal and each lead source counts, currency conversion on or off | "How we rank" tab on the plan page |
| Currency rates, how far back leads count, what counts as shrinking use, AI on or off | `config.yaml`, then `python run.py` |

**A deeper change to try:** switch the AI off (`ai.enabled: false` in `config.yaml`) and run again. Leads with messy names are no longer tied to accounts, so 2 accounts drop out of the Q1 list, 2 others come in, and the pipeline moves from $1.60M to $1.74M. Set it back to `true` and run again to return to the plan.

## If the run stops

When the AI is unsure about a lead, the run stops before building a new plan. Open `data/review_queue.csv`, set `status` to `decided` and fill `decided_account_id` (leave it blank for "not a customer"), `decided_by` and `decided_on`. Then run again. Each decision is saved and reused.

## What's where

```
config.yaml         every assumption, in one place
run.py              runs the whole pipeline
src/                clean, check, match (code + AI), signals, score, export
data/raw/           the 4 CSVs as received
data/lead_labels.csv    answer list used to measure the AI
data/review_queue.csv   leads waiting for, or decided by, a person
output/             results of the last run (checks, matches, ranking, pipeline)
logs/               every change made to the data, step by step
demo/               the plan page and its scoring engine
submission/         the submission page
```
