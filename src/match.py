"""Step 2: match each lead to an account. Code handles the clear cases; the leftovers go to the AI step.

Rule 1  exact:        cleaned lead name == cleaned account name          'IronMedia , Inc.' -> Iron Media Ltd
Rule 2  group suffix: same, once a trailing 'group' is ignored on one side 'Cascade Logistics' -> Cascade Logistics Group
Anything else stays unmatched here. Code never guesses on typos; that is the AI step's job.
"""

import pandas as pd

from src import log


def run(leads, accounts):
    by_key = accounts.set_index("name_key")["account_id"]

    # 'group' is part of some names and a suffix in others; only use it when it points to exactly one account
    stripped = accounts["name_key"].str.replace(r"group$", "", regex=True)
    unique_stripped = stripped[~stripped.duplicated(keep=False)]
    by_stripped = pd.Series(accounts.loc[unique_stripped.index, "account_id"].values, index=unique_stripped.values)

    m = leads[["lead_id", "company", "name_key"]].copy()
    m["account_id"] = m["name_key"].map(by_key)
    m["method"] = m["account_id"].notna().map({True: "exact", False: None})

    # try the lead name as written first ('Redwood Retail Group' -> 'Redwood Retail Group Group'), then without 'group'
    lead_stripped = m["name_key"].where(m["name_key"].isin(by_stripped.index),
                                        m["name_key"].str.replace(r"group$", "", regex=True))
    rule2 = m["account_id"].isna() & lead_stripped.isin(by_stripped.index)
    m.loc[rule2, "account_id"] = lead_stripped[rule2].map(by_stripped)
    m.loc[rule2, "method"] = "group suffix"

    m["method"] = m["method"].fillna("unmatched (to AI step)")
    counts = m["method"].value_counts()
    log.step("leads", "match leads to accounts in code", len(m), len(m),
             ", ".join(f"{k}: {v}" for k, v in counts.items()))
    return m
