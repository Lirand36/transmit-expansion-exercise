"""Step 3: one row per account with the four signals and the flags, measured as of the as_of date.

Intent    leads from the account in the last 90 days, weighted by source       (are they talking to us?)
Headroom  what they pay per active user vs similar accounts in their segment    (are they under-paying for their use?)
Momentum  active-user growth over the last 3 months                             (is use growing?)
Depth     API calls per active user, averaged over 3 months                     (how deeply do they use it?)
"""

import pandas as pd

from src import log


def run(t, matches, cfg):
    a, o, l, u = t["accounts"], t["opportunities"], t["leads"], t["usage"]
    s = cfg["signals"]
    as_of = pd.Timestamp(cfg["dates"]["as_of"])
    out = a[["account_id", "account_name", "segment", "region", "tenant_id"]].copy().set_index("account_id")

    # Customer status from the CRM
    won = o[(o["stage"] == "Closed Won") & (o["close_date"] <= as_of)]
    out["won_deals"] = won.groupby("account_id").size().reindex(out.index, fill_value=0)
    out["paid_to_date_usd"] = won.groupby("account_id")["amount_usd"].sum().reindex(out.index, fill_value=0.0)
    out["last_won_date"] = won.groupby("account_id")["close_date"].max()

    # Intent: weighted leads in the window
    leads = l.merge(matches[["lead_id", "account_id"]], on="lead_id").dropna(subset=["account_id"])
    recent = leads[(leads["created_date"] > as_of - pd.Timedelta(days=s["intent_window_days"]))
                   & (leads["created_date"] <= as_of)].copy()
    recent["weight"] = recent["source"].map(s["lead_source_weight"]).fillna(0.5)
    out["intent_points"] = recent.groupby("account_id")["weight"].sum().reindex(out.index, fill_value=0.0)
    out["recent_leads"] = recent.groupby("account_id").size().reindex(out.index, fill_value=0)
    out["recent_people"] = recent.groupby("account_id")["email"].nunique().reindex(out.index, fill_value=0)

    # Usage signals
    u = u[u["month"] <= as_of].merge(a[["account_id", "tenant_id"]].dropna(), on="tenant_id")
    mau = u.pivot(index="account_id", columns="month", values="monthly_active_users").sort_index(axis=1)
    api = u.pivot(index="account_id", columns="month", values="api_calls").sort_index(axis=1)
    k = s["momentum_months"]
    out["mau_now"] = mau.iloc[:, -1]
    out["momentum_3m"] = mau.iloc[:, -1] / mau.iloc[:, -1 - k] - 1
    out["depth_api_per_user"] = (api.iloc[:, -k:].sum(axis=1) / mau.iloc[:, -k:].sum(axis=1))
    n = s["shrinking_months"]  # needs n+1 months of usage; blank when history is shorter (only happens in backtest.py)
    out["change_6m"] = mau.iloc[:, -1] / mau.iloc[:, -1 - n] - 1 if mau.shape[1] > n else float("nan")

    # Headroom: segment median $ per user divided by the account's $ per user (above 1 = pays less than peers)
    per_user = out["paid_to_date_usd"] / out["mau_now"]
    seg_median = per_user[out["won_deals"] > 0].groupby(out["segment"]).median()
    out["paid_per_user_usd"] = per_user
    out["headroom_ratio"] = out["segment"].map(seg_median) / per_user.where(per_user > 0)

    # Flags
    has_usage = out["mau_now"].notna()
    out["flag_confirm_contract"] = has_usage & (out["won_deals"] == 0)
    # Latest closed deal is a lost renewal, yet they still use the product: contract status needs checking.
    # Shown as an action only; it does not change the score.
    last = o[o["close_date"] <= as_of].sort_values("close_date").groupby("account_id").tail(1).set_index("account_id")
    lost_renewal = (last["type"] == "Renewal") & (last["stage"] == "Closed Lost")
    out["flag_lapsed_renewal"] = has_usage & lost_renewal.reindex(out.index, fill_value=False)
    out["lapsed_renewal_date"] = last["close_date"].where(lost_renewal)
    out["flag_no_usage"] = ~has_usage & (out["won_deals"] > 0)
    out["flag_shrinking"] = out["change_6m"] <= s["shrinking_threshold"]
    out["in_scope"] = (out["won_deals"] > 0) | out["flag_confirm_contract"]

    log.step("signals", "build one row per account", len(a), len(out),
             f"{out['in_scope'].sum()} in scope; {out['flag_confirm_contract'].sum()} confirm-contract; {out['flag_lapsed_renewal'].sum()} lapsed renewal; "
             f"{out['flag_no_usage'].sum()} no usage; {out['flag_shrinking'].sum()} shrinking")
    return out.reset_index()
