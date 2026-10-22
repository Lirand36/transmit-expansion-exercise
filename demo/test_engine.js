// Check: the browser engine gives the same tiers, scores and pipeline as the Python run.  node demo/test_engine.js
const fs = require("fs");
const { compute } = require("./engine.js");
const data = JSON.parse(fs.readFileSync(__dirname + "/../output/demo_data.json"));
const d = data.defaults;
const res = compute(data, { weights: d.weights, sourceWeights: d.sourceWeights, tier1: d.tier1, tier2: d.tier2,
  includeConfirm: d.includeConfirm, convert: d.convert, dealSize: d.dealSize });
const lines = fs.readFileSync(__dirname + "/../output/ranking.csv", "utf8").trim().split("\n");
const head = lines[0].split(",");
const py = {};
for (const line of lines.slice(1)) {
  const c = line.split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/);
  py[c[head.indexOf("account_id")]] = { tier: +c[head.indexOf("tier")], score: +c[head.indexOf("score")] };
}
let bad = 0;
for (const r of res.rows) {
  const p = py[r.id];
  if (!p || p.tier !== r.tier || Math.abs(p.score - r.score) > 1e-9) { bad++; console.log("DIFF", r.id, r.name, p, r.tier, r.score); }
}
console.log(`accounts: js ${res.rows.length}, python ${Object.keys(py).length}, differences: ${bad}`);
console.log("Tier 1 pipeline js:", Math.round(res.pipeline[0].pipeline));
