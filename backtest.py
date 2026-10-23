"""How well would the ranking have picked expansion in the past?

For each month end from Jul 2025 to Feb 2026, the same signals and score as the plan are rebuilt using only
the data known on that date. Then we check which accounts had an expansion deal created in the next 90 days.
Jul 2025 is the first date with 3 months of usage behind it (usage starts Apr 2025), and Feb 2026 the last
whose 90 days are fully covered by the CRM export (it ends 16 Jun 2026). Expansion deals created before
Jul 2025 can't be tested: there is no usage data from before them.

AUC = the chance that an account which went on to expand scored higher than one which didn't.
0.5 is a coin flip, 1.0 is perfect.

Run:  python backtest.py
"""

from pathlib import Path

import pandas as pd
import yaml

from src import ai_match, clean, match, score, signals

BASE = Path(__file__).parent
AS_OF = pd.date_range("2025-07-31", "2026-02-28", freq="ME")
WINDOW = pd.Timedelta(days=90)


def auc(values, labels):
    """Mann-Whitney AUC; ties count half. Accounts with no value for this signal are left out."""
    d = pd.DataFrame({"v": values, "y": labels}).dropna()
    pos, neg = d[d["y"]], d[~d["y"]]
    if pos.empty or neg.empty:
        return None
    r = d["v"].rank()
    return (r[d["y"]].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def main():
    cfg = yaml.safe_load(open(BASE / "config.yaml"))
    t = clean.run(cfg, BASE)
    m = match.run(t["leads"], t["accounts"])
    m, res = ai_match.run(m, t["leads"], t["accounts"], cfg, BASE / "output" / "ai_cache.json")
    m, _ = ai_match.review_gate(m, res, t["accounts"], BASE / "data" / "review_queue.csv")
    exp = t["opportunities"][t["opportunities"]["is_expansion"]]

    rows = []
    for as_of in AS_OF:
        cfg["dates"]["as_of"] = str(as_of.date())
        s = score.score(signals.run(t, m, cfg), cfg)
        ahead = exp[(exp["created_date"] > as_of) & (exp["created_date"] <= as_of + WINDOW)]
        s["expanded"] = s["account_id"].isin(ahead["account_id"])
        s["as_of"] = as_of.date()
        rows.append(s)
    p = pd.concat(rows, ignore_index=True)
    p[["as_of", "account_id", "account_name", "score", "intent_0_100", "headroom_0_100",
       "momentum_0_100", "depth_0_100", "expanded"]].to_csv(BASE / "output" / "backtest.csv", index=False)

    print(f"{len(p)} account-months, {p['expanded'].sum()} went on to expand "
          f"({p.loc[p['expanded'], 'account_id'].nunique()} accounts)\n")
    print(f"Score (the plan's ranking)  AUC {auc(p['score'], p['expanded']):.2f}")
    for name in score.SIGNALS:
        print(f"  {name:<10} alone           AUC {auc(p[f'{name}_0_100'], p['expanded']):.2f}")
    top = p[p.groupby("as_of")["score"].rank(pct=True, ascending=False) <= cfg["scoring"]["tier1_top_share"]]
    print(f"\nTop 20% by score: {top['expanded'].mean():.0%} went on to expand, vs {p['expanded'].mean():.0%} of all accounts")


if __name__ == "__main__":
    main()
