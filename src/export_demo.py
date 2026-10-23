"""Step 5: export what the live demo page needs, as one JSON file. The page redoes the scoring in the browser."""

import json

import pandas as pd

SOURCES = ["Website Demo Request", "Outbound Reply", "Partner Referral", "Review Site", "Paid Search",
           "Webinar", "Conference", "Content Download"]


def run(t, matches, sig, sizes, win_rate, hist, checks, cfg, path):
    as_of = pd.Timestamp(cfg["dates"]["as_of"])
    window = cfg["signals"]["intent_window_days"]
    l = t["leads"].merge(matches[["lead_id", "account_id"]], on="lead_id").dropna(subset=["account_id"])
    recent = l[(l["created_date"] > as_of - pd.Timedelta(days=window)) & (l["created_date"] <= as_of)]
    by_source = recent.groupby(["account_id", "source"]).size().unstack(fill_value=0)
    touches = {a: [{"source": r["source"], "date": r["created_date"].strftime("%-d %b %Y"),
                    "who": f'{r["first_name"]} {r["last_name"]}'.strip()}
                   for _, r in g.sort_values("created_date", ascending=False).iterrows()]
               for a, g in recent.groupby("account_id")}
    months = sorted(t["usage"]["month"].unique())
    k = cfg["signals"]["momentum_months"]
    month_label = lambda m: pd.Timestamp(m).strftime("%b %Y")

    o = t["opportunities"]
    won = o[(o["stage"] == "Closed Won") & (o["close_date"] <= as_of)]
    paid_raw = won.groupby("account_id")["amount"].sum()
    paid_usd = won.groupby("account_id")["amount_usd"].sum()
    recent = won[won["close_date"] > as_of - pd.DateOffset(months=cfg["signals"]["headroom_months"])]
    recent_raw = recent.groupby("account_id")["amount"].sum()
    recent_usd = recent.groupby("account_id")["amount_usd"].sum()
    # Owner = the rep on the account's most recent deal (the CRM has no account owner field)
    owner = o[o["close_date"] <= as_of].sort_values("close_date").groupby("account_id")["owner"].last()

    num = lambda v: None if pd.isna(v) else float(v)
    accounts = []
    for _, r in sig.iterrows():
        a = r["account_id"]
        accounts.append({
            "id": a, "name": r["account_name"], "segment": r["segment"], "region": r["region"],
            "won": int(r["won_deals"]), "paidUsd": float(paid_usd.get(a, 0.0)), "paidRaw": float(paid_raw.get(a, 0.0)),
            "paidRecentUsd": float(recent_usd.get(a, 0.0)), "paidRecentRaw": float(recent_raw.get(a, 0.0)),
            "mau": num(r["mau_now"]), "momentum": num(r["momentum_3m"]), "depth": num(r["depth_api_per_user"]),
            "leads": {s: int(by_source.loc[a, s]) if a in by_source.index and s in by_source.columns else 0
                      for s in SOURCES},
            "touches": touches.get(a, []),
            "owner": owner.get(a, ""),
            "mauPrev": None if pd.isna(r["momentum_3m"]) else round(r["mau_now"] / (1 + r["momentum_3m"])),
            "lapsed": r["lapsed_renewal_date"].strftime("%b %Y") if r["flag_lapsed_renewal"] else None,
            "lastDeal": None if pd.isna(r["last_deal"]) else r["last_deal"],
            "track": r["track"], "inScope": bool(r["in_scope"]), "confirm": bool(r["flag_confirm_contract"]),
            "noUsage": bool(r["flag_no_usage"]), "shrinking": bool(r["flag_shrinking"]),
        })
    data = {
        "asOf": cfg["dates"]["as_of"],
        "defaults": {"weights": cfg["scoring"]["weights"], "sourceWeights": cfg["signals"]["lead_source_weight"],
                     "tier1": cfg["scoring"]["tier1_top_share"], "tier2": cfg["scoring"]["tier2_next_share"],
                     "intentFull": cfg["signals"]["intent_full_points"],
                     "convert": cfg["currency"]["convert_to_usd"], "dealSize": cfg["pipeline"]["deal_size"]},
        "sizes": {b: {r["segment"]: {k: r[k] for k in ["low", "mid", "high"]} | {"deals": int(r["deals"])}
                      for _, r in g.iterrows()} for b, g in sizes.groupby("basis")},
        "winRate": win_rate,
        "history": {"oppRate": hist["opp_rate"], "cycleDays": hist["cycle_days"],
                    "closeInQuarter": hist["close_in_quarter"], "bookedByQuarter": hist["booked_by_quarter"], "createdByQuarter": hist["created_by_quarter"],
                    "oppRateByQuarter": hist["opp_rate_by_quarter"].to_dict("records")},
        "usageMonths": {"now": month_label(months[-1]), "prev": month_label(months[-1 - k])},
        "winBasis": win_basis(o, as_of),
        "checks": checks.fillna("").astype(str).to_dict("records"),
        "accounts": accounts,
    }
    path.write_text(json.dumps(data, indent=1))


def win_basis(o, as_of):
    """Where the expansion win rate comes from, so the page can name the period."""
    e = o[o["is_expansion"]]
    last = e[e["close_date"] > e["close_date"].max() - pd.DateOffset(years=1)]
    return {"won": int((e["stage"] == "Closed Won").sum()), "deals": len(e),
            "from": e["close_date"].min().strftime("%b %Y"), "to": e["close_date"].max().strftime("%b %Y"),
            "last12": float((last["stage"] == "Closed Won").mean()), "last12Deals": len(last)}
