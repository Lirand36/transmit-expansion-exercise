// Scoring engine for the live demo page. Same rules as src/signals.py (headroom, intent) and src/score.py (score, tiers, funnel).
// Kept as a pure function so it can be tested against the Python output (demo/test_engine.js).

// Python and pandas round halves to even; match that so tiers agree exactly.
function roundHalfEven(x, digits) {
  const f = Math.pow(10, digits || 0);
  const v = x * f;
  const r = Math.round(v);
  const isHalf = Math.abs(v % 1) === 0.5;
  return (isHalf ? (r % 2 === 0 ? r : r - 1) : r) / f;
}

function median(values) {
  const v = values.slice().sort((a, b) => a - b);
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

// pandas rank(pct=True): average rank for ties, divided by the number of non-missing values
function pctRank(values) {
  const idx = values.map((v, i) => [v, i]).filter(p => p[0] !== null && !Number.isNaN(p[0]));
  idx.sort((a, b) => a[0] - b[0]);
  const out = values.map(() => null);
  let i = 0;
  while (i < idx.length) {
    let j = i;
    while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++;
    const avg = (i + j + 2) / 2;
    for (let k = i; k <= j; k++) out[idx[k][1]] = avg / idx.length;
    i = j + 1;
  }
  return out;
}

function compute(data, s) {
  const all = data.accounts;

  // Headroom: segment median $ per user / account $ per user, from spend in the last 12 months (signals.py)
  const paid = a => (s.convert ? a.paidRecentUsd : a.paidRecentRaw);
  const perUser = all.map(a => (a.mau ? paid(a) / a.mau : null));
  const segMedian = {};
  for (const seg of ["Enterprise", "Mid-Market", "SMB"]) {
    const v = all.map((a, i) => (a.segment === seg && perUser[i] > 0 ? perUser[i] : null)).filter(x => x !== null);
    segMedian[seg] = median(v);
  }

  let rows = all.map((a, i) => {
    const intent = Object.entries(a.leads)
      .reduce((t, [src, n]) => t + n * (s.sourceWeights[src] !== undefined ? s.sourceWeights[src] : 0.5), 0);
    const headroom = perUser[i] !== null && perUser[i] > 0 ? segMedian[a.segment] / perUser[i] : null;
    return { ...a, intent, headroom };
  }).filter(a => a.inScope);

  const cols = { intent: "intent", headroom: "headroom", momentum: "momentum", depth: "depth" };
  for (const [name, col] of Object.entries(cols)) {
    const p = pctRank(rows.map(r => r[col]));
    rows.forEach((r, i) => { r[name + "100"] = p[i] === null ? null : roundHalfEven(p[i] * 100, 0); });
  }
  // Intent counts leads: points / intentFull, capped at 100 (score.py)
  rows.forEach(r => { r.intent100 = roundHalfEven(Math.min(r.intent / s.intentFull, 1) * 100, 0); });

  rows.forEach(r => {
    let num = 0, den = 0;
    for (const name of Object.keys(cols)) {
      const v = r[name + "100"];
      if (v !== null) { num += v * s.weights[name]; den += s.weights[name]; }
    }
    r.score = den ? roundHalfEven(num / den, 1) : 0;
    r.maxTier = r.noUsage || r.shrinking ? 2 : 1;
    r.capped = r.noUsage ? "no usage data" : r.shrinking ? "shrinking use" : "";
  });

  // Tiers: fill Tier 1 then Tier 2 in score order, skipping capped accounts (stable sort keeps account order)
  rows.sort((a, b) => b.score - a.score);
  // tier1Count = how many accounts the team can work (the CRO's lever); otherwise a share of in-scope accounts
  const n1 = s.tier1Count != null ? s.tier1Count : roundHalfEven(rows.length * s.tier1, 0);
  const n2 = roundHalfEven(rows.length * s.tier2, 0);
  rows.forEach(r => { r.tier = 3; });
  let c1 = 0, c2 = 0;
  for (const r of rows) if (c1 < n1 && r.maxTier <= 1) { r.tier = 1; c1++; }
  for (const r of rows) if (r.tier === 3 && c2 < n2 && r.maxTier <= 2) { r.tier = 2; c2++; }

  const sizes = data.sizes[s.convert ? "converted to USD" : "as recorded"];
  rows.forEach(r => { r.deal = sizes[r.segment][s.dealSize]; r.dealLow = sizes[r.segment].low; r.dealHigh = sizes[r.segment].high; });
  rows.sort((a, b) => a.tier - b.tier || b.score - a.score);

  // Funnel (score.py): accounts x share that open a deal x deal size = pipeline; x win rate = bookings;
  // the share that closes inside Q1 comes from past deal cycles
  const h = data.history;
  const oppRate = s.oppRate != null ? s.oppRate : h.oppRate;
  const win = s.winRate != null ? s.winRate : data.winRate;
  const sum = (tier, key) => rows.filter(r => r.tier === tier).reduce((t, r) => t + r[key], 0);
  const pipeline = [1, 2].map(t => {
    const ifAll = sum(t, "deal"), created = ifAll * oppRate;
    return {
      tier: t, accounts: rows.filter(r => r.tier === t).length, deals: rows.filter(r => r.tier === t).length * oppRate,
      ifAll, pipeline: created, bookings: created * win, bookingsQ1: created * win * h.closeInQuarter,
      low: sum(t, "dealLow") * oppRate, high: sum(t, "dealHigh") * oppRate,
      enterprise: rows.filter(r => r.tier === t && r.segment === "Enterprise").reduce((x, r) => x + r.deal, 0) * oppRate,
    };
  });
  return { rows, pipeline };
}

if (typeof module !== "undefined") module.exports = { compute };
