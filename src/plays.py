"""Step 5: the Q1 plan as plays. Each play = one fact from the data, named accounts, a $ figure, an owner.

The $ figures measure different things, so they are never added up. None is a forecast:
Price to usage      paying customers who pay less per active user than peers in their segment (last 12 months).
                    $ = (peer $ per user - their $ per user) x active users.
Q1 expansion window paying customers whose deals closed in the same quarter a year before the target quarter.
                    $ = what those deals were worth (prior contract value, not expansion value).
Land and expand     customers who landed in the last 12 months, haven't expanded yet and aren't in play 1.
                    Shown as a count of accounts; sorted by one typical past expansion deal in their segment.
Recover revenue     accounts using the product with no won deal (contract check) or after a lost renewal (win-back).
                    $ = their active users x peer $ per user (to be validated).
Risk                paying accounts with no product usage linked. $ = what they paid so far.
The peer benchmark is the segment median by default, or the 25th percentile (config: plays.benchmark).
"""

import pandas as pd

from src import log

BENCH = {"median": 0.50, "low": 0.25}


def run(sig, opps, sizes, cfg):
    p = cfg["plays"]
    as_of = pd.Timestamp(cfg["dates"]["as_of"])
    s = sig.set_index("account_id")
    exp = s[s["track"] == "expansion"]

    per_user = (exp["paid_recent_usd"] / exp["mau_now"]).where(lambda v: v > 0)
    bench = per_user.groupby(exp["segment"]).quantile(BENCH[p["benchmark"]])
    rows = []

    # 1. Price to usage
    gap = (exp["segment"].map(bench) - per_user) * exp["mau_now"]
    for a, v in gap[gap > 0].items():
        rows.append({"play": "price", "account_id": a, "at_stake": v, "per_user": per_user[a],
                     "peer_per_user": bench[exp.at[a, "segment"]], "paid_12m": exp.at[a, "paid_recent_usd"],
                     "fact": f"Pays ${per_user[a]:.2f} per active user; peers pay ${bench[exp.at[a, 'segment']]:.2f}"})

    # 2. Q1 expansion window: deals won in the target quarter, one year earlier
    q_start = pd.Timestamp(cfg["dates"]["target_quarter_start"]) - pd.DateOffset(years=1)
    q_end = pd.Timestamp(cfg["dates"]["target_quarter_end"]) - pd.DateOffset(years=1)
    won = opps[opps["stage"] == "Closed Won"]
    due = won[won["close_date"].between(q_start, q_end) & won["account_id"].isin(exp.index)]
    for a, g in due.groupby("account_id"):
        rows.append({"play": "renewal", "account_id": a, "at_stake": g["amount_usd"].sum(),
                     "fact": "Signed " + ", ".join(f"{t} {d:%b %Y}" for t, d in zip(g["type"], g["close_date"]))})

    # 3. Land and expand: landed in the last 12 months, no expansion deal yet
    first_win = won.groupby("account_id")["close_date"].min()
    expanded = opps[opps["is_expansion"]]["account_id"].unique()
    landed = first_win[(first_win > as_of - pd.DateOffset(months=12)) & (first_win <= as_of)]
    typical = sizes[sizes["basis"] == "converted to USD"].set_index("segment")["mid"]
    for a, d in landed.items():
        if a in exp.index and a not in expanded and not gap.get(a, 0) > 0:  # underpaying ones sit in play 1
            rows.append({"play": "land", "account_id": a, "at_stake": typical[exp.at[a, "segment"]], "landed": d,
                         "fact": f"First deal {d:%b %Y}, no expansion yet"})

    # 4. Recover revenue: contract check and win-back
    for track, why in [("contract", "Uses the product, no won deal on record"),
                       ("winback", "Lost its renewal, still uses the product")]:
        t = s[s["track"] == track]
        for a, r in t.iterrows():
            rows.append({"play": track, "account_id": a, "at_stake": bench[r["segment"]] * r["mau_now"],
                         "fact": why + (f" ({r['last_deal']})" if pd.notna(r["last_deal"]) else "")})

    # Risk: paying accounts with no usage linked
    for a, r in s[s["flag_no_usage"]].iterrows():
        rows.append({"play": "risk", "account_id": a, "at_stake": r["paid_to_date_usd"],
                     "fact": "No usage linked" + (f" (last deal: {r['last_deal']})" if pd.notna(r["last_deal"]) else "")})

    out = pd.DataFrame(rows)
    out = out.merge(sig[["account_id", "account_name", "segment", "region"]], on="account_id")
    out["at_stake"] = out["at_stake"].round()
    log.step("plays", "build the Q1 plays", len(sig), len(out),
             ", ".join(f"{k}: {len(g)} accounts ${g['at_stake'].sum():,.0f}" for k, g in out.groupby("play")))
    out = out.sort_values(["play", "at_stake"], ascending=[True, False])
    out.attrs["peers"] = per_user.dropna().groupby(exp["segment"]).size().to_dict()  # customers behind each peer price
    return out


def facts(opps):
    """Facts the page quotes: how soon after landing expansion happens."""
    e = opps[opps["is_expansion"]]
    days = (e["created_date"] - e["first_win_date"]).dt.days
    return {"expansionWithin90Days": float((days <= 90).mean()), "expansionWithin6Months": float((days <= 182).mean()),
            "expansionDeals": int(len(e))}
