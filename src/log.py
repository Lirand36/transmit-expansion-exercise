"""A small log of every transformation: what was done, to which table, rows before and after."""

import pandas as pd

_entries = []


def step(table, action, rows_before, rows_after, detail=""):
    _entries.append({
        "step": len(_entries) + 1,
        "table": table,
        "action": action,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "detail": detail,
    })


def save(path):
    pd.DataFrame(_entries).to_csv(path, index=False)
    return pd.DataFrame(_entries)
