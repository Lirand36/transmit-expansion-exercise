"""Step 1: load the 4 CSVs and clean them. Every change is written to the transformation log."""

import re
from pathlib import Path

import pandas as pd

from src import log


def company_key(name, suffixes):
    """Turn a company name into a matching key: lower case, no punctuation, no legal suffix, no spaces.
    'IronMedia , Inc.' -> 'ironmedia'   'Quill Bank PLC' -> 'quillbank'"""
    text = name.lower().strip()
    text = re.sub(r"[.,]", " ", text)
    text = re.sub(r"\b(" + "|".join(suffixes) + r")\b", " ", text)
    return re.sub(r"[^a-z]", "", text)


def load(cfg, base):
    folder = (base / cfg["data"]["folder"]).resolve()
    read = lambda key: pd.read_csv(folder / cfg["data"][key], dtype=str, keep_default_na=False)
    tables = {k: read(k) for k in ["accounts", "opportunities", "leads", "usage"]}
    for name, df in tables.items():
        log.step(name, "load", len(df), len(df), f"{len(df.columns)} columns from {cfg['data'][name]}")
    return tables


def clean_accounts(a, cfg):
    a = a.copy()
    a["account_name"] = a["account_name"].str.strip()
    a["tenant_id"] = a["tenant_id"].str.strip().replace("", pd.NA)
    a["created_date"] = pd.to_datetime(a["created_date"])
    a["name_key"] = a["account_name"].map(lambda s: company_key(s, cfg["company_suffixes"]))
    log.step("accounts", "blank tenant_id set to missing", len(a), len(a),
             f"{a['tenant_id'].isna().sum()} accounts have no tenant (no usage can be linked)")
    log.step("accounts", "build name_key for matching", len(a), len(a), "lower case, no punctuation or legal suffix")
    return a


def clean_opportunities(o, cfg):
    o = o.copy()
    before = len(o)
    # Exact duplicates: every field identical except the opportunity_id. Keep the lowest id.
    same_fields = [c for c in o.columns if c != "opportunity_id"]
    o = o.sort_values("opportunity_id")
    dupes = o[o.duplicated(same_fields, keep="first")]
    o = o.drop(dupes.index)
    log.step("opportunities", "drop exact duplicates", before, len(o),
             "dropped " + (", ".join(dupes["opportunity_id"]) or "none"))

    o["amount"] = o["amount"].astype(float)
    for c in ["close_date", "created_date"]:
        o[c] = pd.to_datetime(o[c])

    rates = cfg["currency"]["rates_to_usd"]
    if cfg["currency"]["convert_to_usd"]:
        o["amount_usd"] = o["amount"] * o["currency"].map(rates)
        detail = "converted at " + ", ".join(f"{k} {v}" for k, v in rates.items())
    else:
        o["amount_usd"] = o["amount"]
        detail = "conversion OFF: amounts used as recorded"
    log.step("opportunities", "amount to USD", len(o), len(o), detail)

    # Expansion = Upsell, or New Business created after the account's first won deal closed.
    first_win = o[o["stage"] == "Closed Won"].groupby("account_id")["close_date"].min()
    o["first_win_date"] = o["account_id"].map(first_win)
    nb_on_customer = (o["type"] == "New Business") & (o["created_date"] > o["first_win_date"])
    o["is_expansion"] = (o["type"] == "Upsell") | nb_on_customer
    log.step("opportunities", "flag expansion deals", len(o), len(o),
             f"{(o['type'] == 'Upsell').sum()} Upsell + {nb_on_customer.sum()} New Business on existing customers")
    return o


def clean_leads(l, cfg):
    l = l.copy()
    l["company_clean"] = l["company"].str.strip().str.replace(r"\s+", " ", regex=True)
    l["name_key"] = l["company"].map(lambda s: company_key(s, cfg["company_suffixes"]))
    l["email_domain"] = l["email"].str.split("@").str[1]
    l["created_date"] = pd.to_datetime(l["created_date"])
    l["mql_date"] = pd.to_datetime(l["mql_date"].replace("", pd.NA))
    log.step("leads", "tidy company text and build name_key", len(l), len(l),
             f"{(l['company'] != l['company'].str.strip()).sum()} names had stray spaces")

    # Business rule: outbound leads are never MQL'd, so an MQL date on an outbound lead is not trusted.
    l["is_outbound"] = l["source"].isin(cfg["leads"]["outbound_sources"])
    stamped = l["is_outbound"] & l["mql_date"].notna()
    l["mql_date_trusted"] = l["mql_date"].where(~l["is_outbound"])
    log.step("leads", "ignore MQL dates on outbound leads", len(l), len(l),
             f"{stamped.sum()} outbound leads had an MQL date; set aside")
    return l


def clean_usage(u):
    u = u.copy()
    u["monthly_active_users"] = u["monthly_active_users"].astype(int)
    u["api_calls"] = u["api_calls"].astype(int)
    u["month"] = pd.to_datetime(u["month"] + "-01")
    log.step("usage", "parse numbers and months", len(u), len(u), "")
    return u


def run(cfg, base):
    t = load(cfg, base)
    return {
        "accounts": clean_accounts(t["accounts"], cfg),
        "opportunities": clean_opportunities(t["opportunities"], cfg),
        "leads": clean_leads(t["leads"], cfg),
        "usage": clean_usage(t["usage"]),
    }
