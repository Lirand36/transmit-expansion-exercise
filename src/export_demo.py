"""Step 6: export what the plan page needs, as one JSON file."""

import json

import pandas as pd


def run(t, matches, sig, plays_by_bench, hist, facts, checks, cfg, path):
    as_of = pd.Timestamp(cfg["dates"]["as_of"])
    o = t["opportunities"]
    # Owner = the rep on the account's most recent deal (the CRM has no account owner field)
    owner = o[o["close_date"] <= as_of].sort_values("close_date").groupby("account_id")["owner"].last()

    # Demo requests in the last 90 days: shown as a note for the rep, not scored
    window = cfg["signals"]["intent_window_days"]
    l = t["leads"].merge(matches[["lead_id", "account_id"]], on="lead_id").dropna(subset=["account_id"])
    demo = l[(l["source"] == "Website Demo Request") & (l["created_date"] > as_of - pd.Timedelta(days=window))
             & (l["created_date"] <= as_of)].sort_values("created_date").groupby("account_id").last()
    demo_note = {a: f'{r["first_name"]} {r["last_name"]} asked for a demo on {r["created_date"]:%-d %b %Y}'
                 for a, r in demo.iterrows()}

    s = sig.set_index("account_id")
    num = lambda v: None if pd.isna(v) else float(v)

    def rows(p):
        return [{"play": r["play"], "id": r["account_id"], "name": r["account_name"], "segment": r["segment"],
                 "region": r["region"], "atStake": float(r["at_stake"]), "fact": r["fact"],
                 "owner": owner.get(r["account_id"], ""), "users": num(s.at[r["account_id"], "mau_now"]),
                 "growth": num(s.at[r["account_id"], "momentum_3m"]), "demo": demo_note.get(r["account_id"]),
                 "perUser": num(r.get("per_user")), "peerPerUser": num(r.get("peer_per_user")),
                 "paid12m": num(r.get("paid_12m")),
                 "landed": r["landed"].strftime("%b %Y") if pd.notna(r.get("landed")) else None}
                for _, r in p.iterrows()]

    no_usage = s[s["flag_no_usage"]]
    booked = hist["booked_by_quarter"]
    data = {
        "asOf": cfg["dates"]["as_of"],
        "benchmark": cfg["plays"]["benchmark"],
        "plays": {b: rows(p) for b, p in plays_by_bench.items()},
        "peers": {k: int(v) for k, v in next(iter(plays_by_bench.values())).attrs["peers"].items()},
        "facts": facts,
        "bookedByQuarter": booked,
        "noUsage": {"accounts": int(len(no_usage)), "paidUsd": float(no_usage["paid_to_date_usd"].sum())},
        "checks": checks.fillna("").astype(str).to_dict("records"),
    }
    path.write_text(json.dumps(data, indent=1))
