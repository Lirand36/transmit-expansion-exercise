"""Step 4: score every in-scope account, put it in a tier, and size the Q1 pipeline.

Score    each signal becomes 0-100 (its rank among in-scope accounts), then a weighted average.
         A missing signal is left out and the other weights are scaled up, so nobody is punished for a blank.
Tiers    top 20% = Tier 1, next 30% = Tier 2, rest = Tier 3. Two caps: no usage data or shrinking use -> Tier 2 at most.
Pipeline one expansion deal per account, sized at what past expansion deals in its segment closed at.
         Shown both ways: currency converted to USD, and amounts as recorded.
"""

import pandas as pd

from src import log

SIGNALS = {"intent": "intent_points", "headroom": "headroom_ratio",
           "momentum": "momentum_3m", "depth": "depth_api_per_user"}
SIZE_PCT = {"low": 0.25, "mid": 0.50, "high": 0.75}


def score(sig, cfg):
    sc = cfg["scoring"]
    s = sig.copy()
    scope = s["in_scope"] & (sc["include_confirm_contract"] | ~s["flag_confirm_contract"])
    s = s[scope].copy()

    # Using the product but $0 paid on record = the most headroom possible
    s.loc[s["flag_confirm_contract"], "headroom_ratio"] = s["headroom_ratio"].max()

    for name, col in SIGNALS.items():
        s[f"{name}_0_100"] = (s[col].rank(pct=True) * 100).round(0)
    s.loc[s["intent_points"] == 0, "intent_0_100"] = 0  # no recent leads = no intent

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


def pipeline(ranked, sizes, win_rate, cfg):
    size = cfg["pipeline"]["deal_size"]
    rows = []
    for basis, sz in sizes.groupby("basis"):
        per_seg = sz.set_index("segment")
        for tier in [1, 2]:
            accts = ranked[ranked["tier"] == tier]
            value = accts["segment"].map(per_seg[size]).sum()
            rows.append({"basis": basis, "tier": tier, "accounts": len(accts),
                         "pipeline": round(value), "expected_bookings": round(value * win_rate),
                         "low": round(accts["segment"].map(per_seg["low"]).sum()),
                         "high": round(accts["segment"].map(per_seg["high"]).sum())})
    return pd.DataFrame(rows)
