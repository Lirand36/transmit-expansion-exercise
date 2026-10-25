"""Step 2b: the AI step. Match the leads that code could not match (typos, missing words, companies we don't know).

Why AI here: deciding whether 'Dunore Media Ltd.' is 'Dunmore Media Group' but 'Sable Holdings' is NOT 'Blue Holdings'
is judgement about names, not arithmetic. Fuzzy string scores get both wrong in opposite directions.

Code first shortlists the closest account names for each lead, so the AI only chooses among real accounts or says
"none". Every answer is cached, so re-runs cost nothing and give the same result. Answers below the accept
confidence never reach the ranking.
"""

import difflib
import hashlib
import json
import os
import time
import urllib.request

import pandas as pd

from src import log

PROMPT = """You match sales leads to customer accounts. Company names in leads are typed by people: expect typos,
missing letters, extra legal suffixes (Inc, Ltd, LLC, Group) and odd capitalisation.

For each lead, pick the ONE account from its candidate list that is the same company, or answer null if none is.
Rules:
- Same company = same brand AND same business line, allowing typos. "Dunore Media Ltd." = "Dunmore Media Group".
- Sharing one word is not enough. "Sable Holdings" is NOT "Blue Holdings". "Iron Stores" is NOT "Union Stores".
- A different business line of the same brand is a different company. "Dunmore Stores" is NOT "Dunmore Systems".
- If unsure, answer null. A wrong match is worse than no match.

Return a JSON list, one object per lead, in the same order:
{"lead_id": "...", "account_id": "ACC-... or null", "confidence": 0.0-1.0, "reason": "max 12 words"}

Leads:
"""


def shortlist(lead_key, accounts, n):
    scores = accounts["name_key"].map(lambda k: difflib.SequenceMatcher(None, lead_key, k).ratio())
    top = accounts.assign(score=scores).nlargest(n, "score")
    return [{"account_id": r.account_id, "name": r.account_name} for r in top.itertuples()]


def call_gemini(prompt, model, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.load(r)
            return json.loads(out["candidates"][0]["content"]["parts"][0]["text"])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 2:  # rate limit or busy: wait and retry
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except TimeoutError:
            if attempt < 1:
                continue
            raise


def ckey(item, n):
    return item["cache_key"] if n == 1 else f'{item["cache_key"]}:{n}'


def fill_cache(items, n, cache, cache_path, ai):
    """Ask the AI about every lead not yet answered in pass n. Answers are saved, so re-runs cost nothing."""
    missing = [i for i in items if ckey(i, n) not in cache]
    if not missing:
        return
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("AI step: set GEMINI_API_KEY, or switch the step off in config.yaml (ai.enabled: false).")
    models = [ai["model"]] + ai.get("fallback_models", [])
    for start in range(0, len(missing), ai["batch_size"]):
        batch = missing[start:start + ai["batch_size"]]
        payload = [{k: i[k] for k in ["lead_id", "company", "email_domain", "candidates"]} for i in batch]
        answers, used = None, None
        for model in models:  # busy or failing model: try the next one
            try:
                answers = {a["lead_id"]: a for a in call_gemini(PROMPT + json.dumps(payload, indent=1), model, key)}
                used = model
                break
            except Exception as e:
                print(f"  {model} failed ({type(e).__name__}); trying next model")
        if answers is None:  # every model failed: these leads stay unmatched this run and are retried next run
            print(f"  AI unavailable for {len(batch)} leads; left unmatched")
            continue
        for i in batch:
            a = answers.get(i["lead_id"], {"account_id": None, "confidence": 0, "reason": "no answer returned"})
            valid = {c["account_id"] for c in i["candidates"]}
            if a.get("account_id") not in valid:  # the AI may only pick from the shortlist
                a = {**a, "account_id": None}
            cache[ckey(i, n)] = {"account_id": a.get("account_id"), "confidence": float(a.get("confidence") or 0),
                                 "reason": a.get("reason", ""), "model": used}
        cache_path.write_text(json.dumps(cache, indent=1))


def review_gate(matches, res, accounts, queue_path):
    """Unsure answers wait in a review table. A person's decision is reused every run.
    While anything is still open, no new priority list is made."""
    cols = ["lead_id", "company", "suggested_account_id", "suggested_account", "why_in_review",
            "status", "decided_account_id", "decided_by", "decided_on"]
    q = pd.read_csv(queue_path, keep_default_na=False, dtype=str) if queue_path.exists() else pd.DataFrame(columns=cols)
    names = accounts.set_index("account_id")["account_name"]
    new = res[(res["decision"] == "needs review") & ~res["lead_id"].isin(q["lead_id"])]
    if not new.empty:
        q = pd.concat([q, pd.DataFrame({
            "lead_id": new["lead_id"], "company": new["company"], "suggested_account_id": new["account_id"].fillna(""),
            "suggested_account": new["account_id"].map(names).fillna(""), "why_in_review": new["why_review"],
            "status": "open", "decided_account_id": "", "decided_by": "", "decided_on": ""})], ignore_index=True)
        q.to_csv(queue_path, index=False)

    out = matches.copy()
    done = q[q["status"] == "decided"].set_index("lead_id")
    idx = out["lead_id"].isin(done.index)
    out.loc[idx, "account_id"] = out.loc[idx, "lead_id"].map(done["decided_account_id"]).replace("", None)
    out.loc[idx, "method"] = "person (review)"
    open_items = q[q["status"] == "open"]
    log.step("leads", "review table", len(q), len(open_items), f"{len(open_items)} open, {len(done)} decided by a person")
    return out, open_items


def run(matches, leads, accounts, cfg, cache_path):
    ai = cfg["ai"]
    todo = matches[matches["method"] == "unmatched (to AI step)"]
    if not ai["enabled"] or todo.empty:
        log.step("leads", "AI step", len(matches), len(matches), "switched off" if not ai["enabled"] else "nothing to do")
        return matches, pd.DataFrame()

    domains = leads.set_index("lead_id")["email_domain"]
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    items = []
    for r in todo.itertuples():
        cands = shortlist(r.name_key, accounts, ai["candidates"])
        item = {"lead_id": r.lead_id, "company": r.company.strip(), "email_domain": domains.get(r.lead_id, ""),
                "candidates": cands}
        item["cache_key"] = hashlib.sha256(json.dumps(
            [item["company"], item["email_domain"], cands, ai["model"], ai["prompt_version"]]).encode()).hexdigest()
        items.append(item)

    # Ask twice. If the two answers differ, the AI is unsure, and a person decides.
    for n in (1, 2):
        fill_cache(items, n, cache, cache_path, ai)

    blank = {"account_id": None, "confidence": 0.0, "reason": "AI unavailable this run", "model": None}
    rows = []
    for i in items:
        a1, a2 = cache.get(ckey(i, 1), blank), cache.get(ckey(i, 2), blank)
        best = max([a1, a2], key=lambda a: (a["account_id"] is not None, a["confidence"]))
        if a1["account_id"] is None and a2["account_id"] is None:
            decision, why = "no match", ""
        elif a1["account_id"] != a2["account_id"]:
            decision, why = "needs review", "the two answers disagree"
        elif min(a1["confidence"], a2["confidence"]) >= ai["accept_confidence"]:
            decision, why = "match", ""
        elif min(a1["confidence"], a2["confidence"]) >= ai["review_confidence"]:
            decision, why = "needs review", "low confidence"
        else:
            decision, why = "no match", ""
        rows.append({"lead_id": i["lead_id"], "company": i["company"], **best, "decision": decision,
                     "why_review": why, "answer_1": a1["account_id"], "answer_2": a2["account_id"]})
    res = pd.DataFrame(rows)

    out = matches.copy()
    accepted = res[res["decision"] == "match"].set_index("lead_id")
    idx = out["lead_id"].isin(accepted.index)
    out.loc[idx, "account_id"] = out.loc[idx, "lead_id"].map(accepted["account_id"])
    out.loc[idx, "method"] = "AI"
    review = res[res["decision"] == "needs review"]["lead_id"]
    out.loc[out["lead_id"].isin(review), "method"] = "AI: needs review"
    out.loc[out["method"] == "unmatched (to AI step)", "method"] = "AI: no match"

    counts = res["decision"].value_counts()
    agree = (res["answer_1"].fillna("-") == res["answer_2"].fillna("-")).sum()
    log.step("leads", "AI step: match leftover leads", len(todo), len(todo),
             f"{ai['model']}; two answers agree on {agree} of {len(res)}; "
             + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    return out, res


def evaluate(res, labels_path):
    """Compare the AI's answers with the hand-checked answer key."""
    lab = pd.read_csv(labels_path, keep_default_na=False)
    d = res.merge(lab[["lead_id", "true_account_id"]], on="lead_id")
    used = d["decision"] == "match"
    truth = d["true_account_id"] != ""
    correct = used & (d["account_id"] == d["true_account_id"])
    summary = {
        "leads checked": len(d),
        "real matches in answer key": int(truth.sum()),
        "AI matches used": int(used.sum()),
        "correct matches": int(correct.sum()),
        "wrong matches": int((used & ~correct).sum()),
        "real matches missed": int((truth & ~correct).sum()),
        "sent to review": int((d["decision"] == "needs review").sum()),
    }
    d["verdict"] = "correct no match"
    d.loc[correct, "verdict"] = "correct match"
    d.loc[used & ~correct, "verdict"] = "WRONG match"
    d.loc[~used & truth, "verdict"] = "missed"
    return summary, d
