"""Run the whole pipeline:  python run.py

Reads the 4 CSVs, cleans them, runs the data checks, and writes everything to output/ and logs/.
All assumptions are in config.yaml.
"""

import runpy
from pathlib import Path

import pandas as pd
import yaml

from src import ai_match, checks, clean, export_demo, log, match, plays, score, signals

BASE = Path(__file__).parent


def main():
    cfg = yaml.safe_load(open(BASE / "config.yaml"))

    print("\n1. Load and clean")
    tables = clean.run(cfg, BASE)
    for name, df in tables.items():
        df.to_csv(BASE / "output" / f"clean_{name}.csv", index=False)
    steps = log.save(BASE / "logs" / "transform_log.csv")
    print(steps[["table", "action", "rows_before", "rows_after", "detail"]].to_string(index=False))

    print("\n2. Data checks")
    result = checks.run(tables, cfg)
    result.to_csv(BASE / "output" / "data_checks.csv", index=False)
    print(result.to_string(index=False))
    if (result["status"] == "FAIL").any():
        raise SystemExit("\nA data check FAILED. Stopping before any scoring.")

    print("\n3. Match leads to accounts (code rules)")
    matches = match.run(tables["leads"], tables["accounts"])
    matches.to_csv(BASE / "output" / "lead_matches.csv", index=False)
    log.save(BASE / "logs" / "transform_log.csv")
    print(matches["method"].value_counts().to_string())

    print("\n3b. AI step: leads code could not match")
    matches, ai_res = ai_match.run(matches, tables["leads"], tables["accounts"], cfg, BASE / "output" / "ai_cache.json")
    matches.to_csv(BASE / "output" / "lead_matches.csv", index=False)
    log.save(BASE / "logs" / "transform_log.csv")
    if not ai_res.empty:
        ai_res.to_csv(BASE / "output" / "ai_matches.csv", index=False)
        summary, detail = ai_match.evaluate(ai_res, BASE / "data" / "lead_labels.csv")
        detail.to_csv(BASE / "output" / "ai_eval.csv", index=False)
        for k, v in summary.items():
            print(f"  {k}: {v}")
        matches, open_items = ai_match.review_gate(matches, ai_res, tables["accounts"], BASE / "data" / "review_queue.csv")
        matches.to_csv(BASE / "output" / "lead_matches.csv", index=False)
        log.save(BASE / "logs" / "transform_log.csv")
        if len(open_items):
            print(open_items[["lead_id", "company", "suggested_account", "why_in_review"]].to_string(index=False))
            raise SystemExit(f"\n{len(open_items)} leads are waiting for a person in data/review_queue.csv. "
                             "No new priority list until they are decided.")
    print(matches["method"].value_counts().to_string())

    print("\n4. Account signals")
    sig = signals.run(tables, matches, cfg)
    sig.to_csv(BASE / "output" / "account_signals.csv", index=False)
    print(log.save(BASE / "logs" / "transform_log.csv").iloc[-1]["detail"])

    print("\n5. Account score (tested in backtest.py) and deal history")
    ranked = score.score(sig, cfg)
    sizes, win_rate = score.deal_sizes(tables["opportunities"], sig)
    hist = score.history(tables["opportunities"], cfg)
    ranked.to_csv(BASE / "output" / "ranking.csv", index=False)
    sizes.to_csv(BASE / "output" / "deal_sizes.csv", index=False)
    log.save(BASE / "logs" / "transform_log.csv")
    print(f"Typical expansion deal: " + ", ".join(f"{r['segment']} ${r['mid']:,.0f}" for _, r in sizes[sizes['basis'] == 'converted to USD'].iterrows()))

    print("\n6. Q1 plays")
    by_bench = {}
    for bench in ["median", "low"]:
        by_bench[bench] = plays.run(sig, tables["opportunities"], sizes, {**cfg, "plays": {"benchmark": bench}})
    p = by_bench[cfg["plays"]["benchmark"]]
    show_moves(p)
    p.to_csv(BASE / "output" / "plays.csv", index=False)
    log.save(BASE / "logs" / "transform_log.csv")
    for name, g in p.groupby("play", sort=False):
        print(f"  {name:<9} {len(g):>3} accounts  ${g['at_stake'].sum():>12,.0f}")

    # Forecast context: the score's top 20% x typical expansion deal x share of customers who open one a quarter
    mid = sizes[sizes["basis"] == "converted to USD"].set_index("segment")["mid"]
    forecast = float(ranked.loc[ranked["tier"] == 1, "segment"].map(mid).sum() * hist["opp_rate"])
    print(f"  Forecast context (score's top 20%, past rates): ${forecast:,.0f} of expansion pipeline")
    export_demo.run(tables, matches, sig, by_bench, hist, {**plays.facts(tables["opportunities"]), "forecast": forecast}, result, cfg,
                    BASE / "output" / "demo_data.json")
    print("\nPlan data written to output/demo_data.json")
    runpy.run_path(str(BASE / "demo" / "build_page.py"))


def show_moves(p):
    """Compare with the previous run, so a live change shows what moved."""
    last = BASE / "output" / "plays.csv"
    if not last.exists():
        return
    old = pd.read_csv(last)
    print("What moved since the last run:")
    key = lambda d: set(zip(d["play"], d["account_name"]))
    for play, name in sorted(key(p) - key(old)):
        print(f"  + {name} joins {play}")
    for play, name in sorted(key(old) - key(p)):
        print(f"  - {name} leaves {play}")
    for play in p["play"].unique():
        o, n = old.loc[old["play"] == play, "at_stake"].sum(), p.loc[p["play"] == play, "at_stake"].sum()
        if round(o) != round(n):
            print(f"  {play}: ${o:,.0f} -> ${n:,.0f}")


if __name__ == "__main__":
    main()
