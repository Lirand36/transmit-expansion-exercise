"""Run the whole pipeline:  python run.py

Reads the 4 CSVs, cleans them, runs the data checks, and writes everything to output/ and logs/.
All assumptions are in config.yaml.
"""

import runpy
from pathlib import Path

import pandas as pd
import yaml

from src import ai_match, checks, clean, export_demo, log, match, score, signals

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

    print("\n5. Score, tiers and Q1 2027 pipeline")
    ranked = score.score(sig, cfg)
    sizes, win_rate = score.deal_sizes(tables["opportunities"], sig)
    hist = score.history(tables["opportunities"], cfg)
    pipe = score.pipeline(ranked, sizes, win_rate, hist, cfg)
    show_moves(ranked, pipe)
    ranked.to_csv(BASE / "output" / "ranking.csv", index=False)
    sizes.to_csv(BASE / "output" / "deal_sizes.csv", index=False)
    pipe.to_csv(BASE / "output" / "pipeline.csv", index=False)
    log.save(BASE / "logs" / "transform_log.csv")

    cols = ["account_name", "segment", "score", "intent_0_100", "headroom_0_100", "momentum_0_100",
            "depth_0_100"]
    print("\nTier 1 accounts:")
    print(ranked[ranked["tier"] == 1][cols].to_string(index=False))
    print(f"\nDeal size used: {cfg['pipeline']['deal_size']}. Expansion win rate: {win_rate:.0%}. "
          f"Customers opening an expansion deal per quarter: {hist['opp_rate']:.1%}. "
          f"Median cycle {hist['cycle_days']:.0f} days, so {hist['close_in_quarter']:.0%} of a quarter's new pipeline closes in it.")
    print(pipe.to_string(index=False))
    for track, who in [("contract", "Contract check (RevOps with Finance)"), ("winback", "Win-back (Customer Success)")]:
        print(f"\n{who}: " + ", ".join(sig.loc[sig["track"] == track, "account_name"]))

    export_demo.run(tables, matches, sig, sizes, win_rate, hist, result, cfg, BASE / "output" / "demo_data.json")
    print("\nDemo data written to output/demo_data.json")
    runpy.run_path(str(BASE / "demo" / "build_page.py"))


def show_moves(ranked, pipe):
    """Compare with the previous run, so a live change shows what moved."""
    last_rank, last_pipe = BASE / "output" / "ranking.csv", BASE / "output" / "pipeline.csv"
    if not last_rank.exists():
        return
    before = pd.read_csv(last_rank).set_index("account_name")["tier"]
    after = ranked.set_index("account_name")["tier"]
    joined = pd.concat([before.rename("before"), after.rename("after")], axis=1)
    moved = joined[joined["before"].fillna(0) != joined["after"].fillna(0)]
    print("\nWhat moved since the last run:")
    if moved.empty:
        print("  no tier changes")
    for name, r in moved.iterrows():
        b = "out" if pd.isna(r["before"]) else f"Tier {int(r['before'])}"
        a = "out" if pd.isna(r["after"]) else f"Tier {int(r['after'])}"
        print(f"  {name}: {b} -> {a}")
    old = pd.read_csv(last_pipe)
    for basis in pipe["basis"].unique():
        o = old[(old["basis"] == basis) & (old["tier"] == 1)]["pipeline"].sum()
        n = pipe[(pipe["basis"] == basis) & (pipe["tier"] == 1)]["pipeline"].sum()
        print(f"  Tier 1 pipeline ({basis}): {o:,.0f} -> {n:,.0f}")


if __name__ == "__main__":
    main()
