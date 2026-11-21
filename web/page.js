// Fills the page from feeds/status.json and feeds/history.json. Nothing else.
const el = (id) => document.getElementById(id);
const num = (x) => (x == null ? "–" : Number(x).toLocaleString("en-US"));
const pct = (x) => (x == null ? "–" : (x * 100).toFixed(1) + "%");

function since(iso) {
  const h = (Date.now() - new Date(iso)) / 36e5;
  if (h < 1) return "minutes ago";
  if (h < 36) return `${Math.round(h)} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

function rows(id, items, render) {
  const body = el(id).querySelector("tbody");
  body.innerHTML = "";
  if (!items || !items.length) {
    body.innerHTML = `<tr><td colspan="8" class="note">nothing to show</td></tr>`;
    return;
  }
  for (const it of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = render(it).map(([html, cls]) => `<td class="${cls || ""}">${html}</td>`).join("");
    body.appendChild(tr);
  }
}

function bar(value, max) {
  const w = max ? Math.max(4, Math.round((value / max) * 100)) : 0;
  return `<div class="bar"><span style="width:${w}%"></span></div>`;
}

function drawSeries(points) {
  const svg = el("spark");
  svg.innerHTML = "";
  const ys = points.map((p) => p.patients || 0);
  if (!ys.length) return;
  const W = 560, H = 170, L = 8, R = 8, T = 18, B = 26;
  const top = Math.max(...ys, 1);
  const x = (i) => (ys.length === 1 ? W / 2 : L + (i / (ys.length - 1)) * (W - L - R));
  const y = (v) => H - B - (v / top) * (H - T - B);
  const pts = ys.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  svg.innerHTML =
    `<path class="area" d="M${x(0)},${H - B} L${pts.join(" L")} L${x(ys.length - 1)},${H - B} Z"/>` +
    `<path d="M${pts.join(" L")}"/>` +
    ys.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="4"/>`).join("") +
    `<text x="${L}" y="${H - 6}">${points[0].week}</text>` +
    `<text x="${W - R}" y="${H - 6}" text-anchor="end">${points[points.length - 1].week}</text>` +
    `<text x="${L}" y="${T - 5}">${num(top)} at the peak</text>`;
}

async function feed(name) {
  const r = await fetch(`feeds/${name}.json`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  return r.json();
}

(async () => {
  let s;
  try {
    s = await feed("status");
  } catch (e) {
    el("fresh").classList.add("down");
    el("fresh-text").textContent = "status.json is not published yet";
    return;
  }
  const c = s.counts || {};
  el("fresh-text").textContent = `built ${since(s.built_at)} · ${(s.cohorts || []).length} cohort(s) · ${num(s.dbt?.models)} dbt models · lake ${(s.lake_bytes / 1e6).toFixed(0)} MB`;
  el("n-patients").textContent = num(c.patients);
  el("n-encounters").textContent = num(c.encounters);
  el("n-results").textContent = num(c.results);
  el("n-diagnoses").textContent = num(c.diagnoses);
  el("n-rejects").textContent = num(c.rejects);
  el("n-tests").innerHTML = s.dbt?.tests ? `${num(s.dbt.tests_ok)}<small>/${num(s.dbt.tests)}</small>` : "–";

  const pairs = s.pairs || [];
  const maxLift = Math.max(...pairs.map((p) => p.lift || 0), 1);
  rows("pairs", pairs, (p) => [
    [`${p.bucket_a}<span class="plus">+</span>${p.bucket_b}`],
    [num(p.both_n), "r"],
    [pct(p.share), "r hide-sm"],
    [`<span class="pill">${Number(p.lift).toFixed(2)}×</span> ${bar(p.lift, maxLift)}`],
  ]);

  const g = s.care_gaps || {};
  el("g-statin").textContent = pct(g.statin_share);
  el("g-statin-den").textContent = `${num(g.statin_in_year)} of ${num(g.statin_eligible)} aged 40 to 75 at diagnosis`;
  el("g-a1c").textContent = pct(g.a1c_share);
  el("g-a1c-den").textContent = `${num(g.a1c_in_90d)} of ${num(g.diabetics)} diabetics`;
  rows("gaps-payer", g.by_payer, (r) => [[r.payer_class], [num(r.diabetics), "r"], [pct(r.statin_share), "r"], [pct(r.a1c_share), "r"]]);
  rows("gaps-age", g.by_bracket, (r) => [[r.age_bracket], [num(r.diabetics), "r"], [pct(r.statin_share), "r"], [pct(r.a1c_share), "r"]]);

  const sc = s.scrub || {};
  rows("ledger", sc.ledger, (r) => [
    [r.table_name],
    [num(r.rows), "r"],
    [num(r.ids_hashed), "r"],
    [num(r.dates_offset), "r"],
    [num(r.free_text_redactions), "r hide-sm"],
    [`<span class="dropped">${(r.dropped_columns || "").split(",").filter(Boolean).join(" · ") || "none"}</span>`],
  ]);
  const k = sc.risk || {};
  if (k.patients) {
    el("risk").textContent = `Re-identification risk on {${k.quasi_identifiers}}: smallest group ${num(k.smallest_group)}, ${num(k.unique_patients)} patients (${pct(k.unique_share)}) are unique, ${pct(k.under_5_share)} sit in groups under 5. Safe Harbor strips identifiers; it does not promise anonymity.`;
  }

  rows("rejects", s.reject_reasons, (r) => [[r.table_name], [r.problem], [num(r.n), "r"]]);
  const nr = Object.entries(s.not_read || {}).sort((a, b) => b[1] - a[1]);
  rows("notread", nr, ([t, n]) => [[t], [num(n), "r"]]);

  try {
    const h = await feed("history");
    drawSeries(h);
    const last = h[h.length - 1];
    el("spark-note").textContent = `${h.length} week(s) · latest ${last.week}: ${num(last.patients)} patients, ${num(last.encounters)} encounters, ${num(last.rejects)} rejected`;
  } catch {
    el("spark-note").textContent = "history.json is not published yet";
  }
})();
