"""Step 4: score every expansion account, put it in a tier, and forecast Q1 through the funnel.

Score    intent = weighted leads / 3, capped at 100. Headroom, momentum, depth = rank among expansion accounts, 0-100.
         Then a weighted average. The weights are judgment calls. A missing signal is left out and the
         other weights are scaled up, so nobody is punished for a blank.
Tiers    top 20% = Tier 1, next 30% = Tier 2, rest = Tier 3. Two caps: no usage data or shrinking use -> Tier 2 at most.
Funnel   accounts worked x share that open a deal (history) x deal size = pipeline created.
         Pipeline x win rate = bookings; the share that closes inside Q1 comes from past deal cycles.
         Deal size = what past expansion deals in the segment closed at, converted to USD or as recorded.
"""

import pandas as pd

from src import log

SIGNALS = {"intent": "intent_points", "headroom": "headroom_ratio",
           "momentum": "momentum_3m", "depth": "depth_api_per_user"}
SIZE_PCT = {"low": 0.25, "mid": 0.50, "high": 0.75}


def score(sig, cfg):
    sc = cfg["scoring"]
    s = sig.copy()
    s = s[s["in_scope"]].copy()

    for name, col in SIGNALS.items():
        s[f"{name}_0_100"] = (s[col].rank(pct=True) * 100).round(0)
    # Intent counts leads instead of ranking them: most accounts have 0 or 1 lead, so a rank would overstate small gaps
    s["intent_0_100"] = (s["intent_points"] / cfg["signals"]["intent_full_points"]).clip(upper=1).mul(100).round(0)

    w = pd.Series(sc["weights"])
    parts = s[[f"{n}_0_100" for n in w.index]]
    available = parts.notna().mul(w.values)
    s["score"] = (parts.fillna(0).mul(w.values).sum(axis=1) / available.sum(axis=1)).round(1)

    # Tiers: fill Tier 1 then Tier 2 in score order, skipping accounts capped below that tier
    s = s.sort_values("score", ascending=False, kind="mergesort")  # stable: ties keep account order
    s["max_tier"] = 1
    s["capped"] = ""
    for flag, cap, why in [("flag_no_usage", sc["no_usage_max_tier"], "no usage data"),
                           ("flag_shrinking", sc["shrinking_max_tier"], "shrinking use")]:
        s.loc[s[flag], "max_tier"] = s.loc[s[flag], "max_tier"].clip(lower=cap)
        s.loc[s[flag], "capped"] = why
    n1 = round(len(s) * sc["tier1_top_share"])
    n2 = round(len(s) * sc["tier2_next_share"])
    t1 = s[s["max_tier"] <= 1].head(n1).index
    t2 = s.drop(t1)[s.drop(t1)["max_tier"] <= 2].head(n2).index
    s["tier"] = 3
    s.loc[t2, "tier"] = 2
    s.loc[t1, "tier"] = 1

    log.step("score", "score and tier accounts", len(sig), len(s),
             ", ".join(f"Tier {t}: {n}" for t, n in s["tier"].value_counts().sort_index().items()))
    return s.sort_values(["tier", "score"], ascending=[True, False], kind="mergesort")


def deal_sizes(opps, sig):
    """Past won expansion deals by segment: 25th / 50th / 75th percentile, in USD and as recorded."""
    won = opps[opps["is_expansion"] & (opps["stage"] == "Closed Won")].merge(sig[["account_id", "segment"]])
    rows = []
    for basis, col in [("converted to USD", "amount_usd"), ("as recorded", "amount")]:
        for seg, g in won.groupby("segment"):
            rows.append({"basis": basis, "segment": seg, "deals": len(g),
                         **{k: g[col].quantile(p) for k, p in SIZE_PCT.items()}})
    exp = opps[opps["is_expansion"]]
    win_rate = (exp["stage"] == "Closed Won").mean()
    return pd.DataFrame(rows), win_rate


def history(opps, cfg):
    """What the CRM says about the funnel: how often a customer opens an expansion deal in a quarter,
    how long deals take, and what expansion has booked per quarter (the run rate to reconcile against)."""
    exp = opps[opps["is_expansion"]]
    won = opps[opps["stage"] == "Closed Won"]
    last_full = (opps["created_date"].max() + pd.Timedelta(days=1)).to_period("Q") - 1
    quarters = pd.period_range(end=last_full, periods=cfg["pipeline"]["opp_rate_quarters"], freq="Q")
    rows = []
    for q in quarters:
        customers = won.loc[won["close_date"] < q.start_time, "account_id"].unique()
        opened = exp[exp["created_date"].between(q.start_time, q.end_time) & exp["account_id"].isin(customers)]
        rows.append({"quarter": str(q), "customers": len(customers), "opened": opened["account_id"].nunique()})
    rate = pd.DataFrame(rows)
    # Share of a quarter's new pipeline that also closes in that quarter: a deal with a c-day cycle,
    # created on a random day of a 90-day quarter, closes inside it with chance (90 - c) / 90.
    exp_won = exp[exp["stage"] == "Closed Won"]
    cycle = (exp_won["close_date"] - exp_won["created_date"]).dt.days
    booked = exp_won.groupby(exp_won["close_date"].dt.to_period("Q"))["amount_usd"].sum()
    return {"opp_rate": rate["opened"].sum() / rate["customers"].sum(), "opp_rate_by_quarter": rate,
            "cycle_days": float(cycle.median()), "close_in_quarter": float(((90 - cycle).clip(lower=0) / 90).mean()),
            "booked_by_quarter": {str(q): float(v) for q, v in booked.items()}}


def pipeline(ranked, sizes, win_rate, hist, cfg):
    """Tier 1 and 2 through the funnel: accounts -> deals opened -> pipeline -> bookings in Q1 and later."""
    size = cfg["pipeline"]["deal_size"]
    rows = []
    for basis, sz in sizes.groupby("basis"):
        per_seg = sz.set_index("segment")
        for tier in [1, 2]:
            accts = ranked[ranked["tier"] == tier]
            if_all = accts["segment"].map(per_seg[size]).sum()  # if every account opened a deal
            created = if_all * hist["opp_rate"]
            rows.append({"basis": basis, "tier": tier, "accounts": len(accts),
                         "deals_opened": round(len(accts) * hist["opp_rate"], 1),
                         "pipeline": round(created), "bookings_total": round(created * win_rate),
                         "bookings_q1": round(created * win_rate * hist["close_in_quarter"]),
                         "if_every_account_opens": round(if_all)})
    return pd.DataFrame(rows)
