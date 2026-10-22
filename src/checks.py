"""Data checks that run on every run. PASS = as expected, WARN = known gap that limits the answer, FAIL = stop and look."""

import pandas as pd


def run(t, cfg):
    a, o, l, u = t["accounts"], t["opportunities"], t["leads"], t["usage"]
    as_of = pd.Timestamp(cfg["dates"]["as_of"])
    rows = []

    def check(name, value, ok, bad_status="FAIL", note="", info=False):
        status = "INFO" if info else ("PASS" if ok else bad_status)
        rows.append({"check": name, "value": value, "status": status, "note": note if status != "PASS" else ""})

    # Keys
    check("account_id unique", a["account_id"].duplicated().sum(), a["account_id"].is_unique)
    check("opportunity_id unique", o["opportunity_id"].duplicated().sum(), o["opportunity_id"].is_unique)
    check("lead_id unique", l["lead_id"].duplicated().sum(), l["lead_id"].is_unique)
    dup_tm = u.duplicated(["tenant_id", "month"]).sum()
    check("usage tenant+month unique", dup_tm, dup_tm == 0)

    # Joins
    orphan_opps = (~o["account_id"].isin(a["account_id"])).sum()
    check("every opp has an account", orphan_opps, orphan_opps == 0)
    orphan_usage = (~u["tenant_id"].isin(a["tenant_id"].dropna())).sum()
    check("every usage row has an account", orphan_usage, orphan_usage == 0)
    no_tenant = a["tenant_id"].isna().sum()
    check("accounts without a tenant", no_tenant, no_tenant == 0, "WARN", "no usage can be linked to these")

    # Dates
    bad_close = (o["close_date"] < o["created_date"]).sum()
    check("opp closes before it was created", bad_close, bad_close == 0)
    bad_mql = (l["mql_date"] < l["created_date"]).sum()
    check("MQL before lead was created", bad_mql, bad_mql == 0)
    months = u.groupby("tenant_id")["month"].nunique()
    check("usage months per tenant", f"{months.min()} to {months.max()}", months.min() == months.max(), "WARN",
          "tenants with missing months")

    # Known gaps that limit the answer
    open_opps = (~o["stage"].isin(["Closed Won", "Closed Lost"])).sum()
    check("open opportunities in the CRM", open_opps, open_opps > 0, "WARN", "no open pipeline is visible")
    lag = (as_of - o["close_date"].max()).days
    check("days between last CRM close and as-of date", lag, lag <= 60, "WARN",
          f"CRM data ends {o['close_date'].max().date()}")
    paying = set(o.loc[o["stage"] == "Closed Won", "account_id"])
    with_usage = set(a.loc[a["tenant_id"].isin(u["tenant_id"]), "account_id"])
    used_not_paid = len(with_usage - paying)
    check("accounts with usage but no won deal", used_not_paid, used_not_paid == 0, "WARN",
          "CRM may be missing deals; confirm contracts")
    last = o.sort_values("close_date").groupby("account_id").tail(1)
    lapsed = set(last.loc[(last["type"] == "Renewal") & (last["stage"] == "Closed Lost"), "account_id"]) & with_usage
    check("accounts still using after a lost renewal", len(lapsed), len(lapsed) == 0, "WARN",
          "using the product with no current contract, or the CRM is wrong")
    paid_no_usage = len(paying - with_usage)
    check("paying accounts with no usage", paid_no_usage, paid_no_usage == 0, "WARN",
          "missing tenant link, not onboarded, or churned")
    outbound_mql = (l["is_outbound"] & l["mql_date"].notna()).sum()
    check("outbound leads with an MQL date", outbound_mql, outbound_mql == 0, "WARN",
          "outbound should never be MQL'd; MQL field unreliable")
    demo = l[l["source"] == "Website Demo Request"]
    demo_no_mql = demo["mql_date"].isna().sum()
    check("demo requests never MQL'd", f"{demo_no_mql} of {len(demo)}", demo_no_mql == 0, "WARN",
          "strongest lead type missed by scoring or routing")
    non_usd = (o["currency"] != "USD").mean()
    check("share of opps not in USD", f"{non_usd:.0%}", True, info=True, note="currency labels look unreliable")

    return pd.DataFrame(rows)
