"""Step 6b: the CRO summary. Only what the CRM export shows: no targets, no ARR, no open pipeline.

Each KPI compares the last 4 quarters with the 4 before. The export's last deal closes mid Q2 2026,
so the windows are calendar quarters up to and including that one (the page says where the data ends).
"""

import pandas as pd


def run(opps, accounts):
    o = opps.merge(accounts[["account_id", "segment", "region"]], on="account_id", how="left")
    end = o["close_date"].max()
    last_q = end.to_period("Q")
    windows = {"now": pd.period_range(end=last_q, periods=4, freq="Q"),
               "before": pd.period_range(end=last_q - 4, periods=4, freq="Q")}
    o["q"] = o["close_date"].dt.to_period("Q")
    won = o["stage"] == "Closed Won"
    exp, ren = o[o["is_expansion"]], o[o["type"] == "Renewal"]

    def window(d, w):
        return d[d["q"].isin(windows[w])]

    def kept(d):  # renewal $ won / renewal $ closed
        return float(d.loc[won, "amount_usd"].sum() / d["amount_usd"].sum())

    def win_rate(d):  # share of closed deals that were won
        return float(won[d.index].mean())

    def win_loss(d):
        w = d[won[d.index]]
        l = d[~won[d.index]]
        return {"wonUsd": float(w["amount_usd"].sum()), "won": int(len(w)),
                "lostUsd": float(l["amount_usd"].sum()), "lost": int(len(l))}

    e_won = exp[won[exp.index]]
    by_q = e_won.groupby("q")["amount_usd"].sum()
    quarters = pd.period_range(end=last_q, periods=8, freq="Q")
    recent = window(e_won, "now")
    return {
        "dataEnds": f"{end:%-d %b %Y}",
        "window": f"{windows['now'][0]}–{windows['now'][-1]}".replace("Q", " Q"),
        "expansionBooked": {w: float(window(e_won, w)["amount_usd"].sum()) for w in windows},
        "largestExpansion": float(recent["amount_usd"].max()),
        "expansionByQuarter": [{"q": str(q), "usd": float(by_q.get(q, 0))} for q in quarters],
        "renewalKept": {w: kept(window(ren, w)) for w in windows},
        "expansionWinRate": {w: win_rate(window(exp, w)) for w in windows},
        "bySegment": recent.groupby("segment")["amount_usd"].sum().sort_values(ascending=False).to_dict(),
        "byRegion": recent.groupby("region")["amount_usd"].sum().sort_values(ascending=False).to_dict(),
        "winLoss": {"Expansion": win_loss(window(exp, "now")), "Renewal": win_loss(window(ren, "now"))},
    }
