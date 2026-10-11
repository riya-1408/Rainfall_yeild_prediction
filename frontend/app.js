/* AgriRain Analytics – dependency-free dashboard (vanilla JS + inline SVG). Data comes from data.js. */
(() => {
"use strict";
const D = window.DATA;
const PAL = ["#2e7d32", "#1565c0", "#ef6c00", "#6a1b9a", "#c62828", "#00838f", "#9e9d24", "#ad1457", "#5d4037", "#546e7a"];
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = v => { if (v == null || isNaN(v)) return "–"; const a = Math.abs(v);
  return a >= 1e9 ? (v / 1e9).toFixed(2) + "B" : a >= 1e6 ? (v / 1e6).toFixed(2) + "M" : a >= 1e4 ? (v / 1e3).toFixed(1) + "K"
    : a >= 100 ? Math.round(v).toLocaleString() : a >= 10 ? v.toFixed(1) : v.toFixed(2); };
const pct = v => (v == null ? "–" : v.toFixed(1) + "%");
const [YMIN, YMAX] = D.filters.years;
const S = { tab: "overview", state: "All", crop: "All", season: "All", y0: YMIN, y1: YMAX, by: "state", q: "", sort: {},
  dist: Object.keys(D.district_year)[0] };

/* ---------- data selectors ---------- */
const rows = () => D.cube.filter(r => (S.state === "All" || r[0] === S.state) && (S.crop === "All" || r[1] === S.crop) &&
  (S.season === "All" || r[2] === S.season) && r[3] >= S.y0 && r[3] <= S.y1);
const districts = () => D.districts.filter(d => S.state === "All" || d.state === S.state);
const sum = (rs, i) => rs.reduce((a, r) => a + r[i], 0);
const sumBy = (rs, kf) => { const m = new Map(); rs.forEach(r => m.set(kf(r), (m.get(kf(r)) || 0) + r[4])); return m; };
const top = (m, n) => [...m].sort((a, b) => b[1] - a[1]).slice(0, n).map(([label, value]) => ({ label, value }));

/* ---------- SVG chart primitives ---------- */
const W = 760, H = 320, M = { l: 64, r: 18, t: 16, b: 38 };
const sc = (a, b, c, d) => v => c + (v - a) / ((b - a) || 1) * (d - c);
function ticks(lo, hi, n = 5) {
  const raw = ((hi - lo) || 1) / n, p = 10 ** Math.floor(Math.log10(raw)), f = raw / p, step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p, t = [];
  for (let v = Math.floor(lo / step) * step; v < hi + step * 0.999; v += step) t.push(+v.toFixed(10));
  return t;
}
const empty = () => `<div class="empty">No data for the selected filters — this crop may not be grown in that state / season in the dataset. Try another combination or Reset.</div>`;
const legend = (items) => items.length < 2 ? "" : `<div class="legend">${items.map((s, i) => `<span><i style="background:${s.color || PAL[i % PAL.length]}"></i>${esc(s.name)}</span>`).join("")}</div>`;
const yGrid = (tk, sy, yfmt) => tk.map(v => `<line class="grid" x1="${M.l}" x2="${W - M.r}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${M.l - 8}" y="${sy(v) + 4}" text-anchor="end">${yfmt(v)}</text>`).join("");

function lineChart(series, { yfmt = fmt, lo, hi, xfmt = x => x, labelFirst = false } = {}) {
  series = series.filter(s => s.pts.length); if (!series.length) return empty();
  const xs = [...new Set(series.flatMap(s => s.pts.map(p => p[0])))].sort((a, b) => a - b), ys = series.flatMap(s => s.pts.map(p => p[1]));
  const tk = ticks(lo ?? Math.min(0, ...ys), hi ?? Math.max(...ys)), sy = sc(tk[0], tk[tk.length - 1], H - M.b, M.t);
  const sx = xs.length > 1 ? sc(xs[0], xs[xs.length - 1], M.l, W - M.r) : () => (M.l + W - M.r) / 2, lx = labelFirst ? [...new Set(series[0].pts.map(p => p[0]))].sort((a, b) => a - b) : xs, step = Math.ceil(lx.length / (labelFirst ? 6 : 12));
  let g = yGrid(tk, sy, yfmt) + lx.map((x, i) => i % step ? "" : `<text x="${sx(x)}" y="${H - M.b + 18}" text-anchor="middle">${xfmt(x)}</text>`).join("");
  series.forEach((s, i) => {
    const c = s.color || PAL[i % PAL.length], pts = s.pts.slice().sort((a, b) => a[0] - b[0]);
    g += `<path d="${pts.map((p, j) => (j ? "L" : "M") + sx(p[0]).toFixed(1) + " " + sy(p[1]).toFixed(1)).join("")}" fill="none" stroke="${c}" stroke-width="2.2"/>`;
    g += pts.map(p => `<circle cx="${sx(p[0]).toFixed(1)}" cy="${sy(p[1]).toFixed(1)}" r="3" fill="${c}"><title>${esc(s.name)} ${xfmt(p[0])}: ${yfmt(p[1])}</title></circle>`).join("");
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${g}</svg>${legend(series)}`;
}

function barH(items, { color, fmtv = fmt, lw = 150 } = {}) {
  if (!items.length) return empty();
  const rh = 26, h = items.length * rh + 12, max = Math.max(...items.map(i => i.value)) || 1, sx = sc(0, max, 0, W - lw - 90);
  return `<svg viewBox="0 0 ${W} ${h}" role="img">${items.map((it, i) => { const y = 6 + i * rh, w = Math.max(sx(it.value), 1);
    return `<text x="${lw - 8}" y="${y + 16}" text-anchor="end">${esc(it.label.length > 24 ? it.label.slice(0, 23) + "…" : it.label)}</text>` +
      `<rect x="${lw}" y="${y + 3}" width="${w}" height="${rh - 8}" rx="3" fill="${it.color || color || PAL[0]}"><title>${esc(it.label)}: ${fmtv(it.value)}</title></rect>` +
      `<text class="val" x="${lw + w + 6}" y="${y + 16}">${fmtv(it.value)}</text>`; }).join("")}</svg>`;
}

function table(id, cols, data, def = { k: cols[0].k, d: -1 }, limit = 200) {
  const st = S.sort[id] || def;
  const rs = data.slice().sort((a, b) => { const x = a[st.k], y = b[st.k]; return (typeof x === "string" ? x.localeCompare(y) : (x ?? -1e99) - (y ?? -1e99)) * st.d; });
  return `<div class="tw"><table><thead><tr>${cols.map(c => `<th data-sort="${id}:${c.k}">${c.label}${st.k === c.k ? (st.d > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead><tbody>` +
    rs.slice(0, limit).map(r => `<tr>${cols.map(c => `<td>${c.f ? c.f(r[c.k], r) : esc(r[c.k] ?? "–")}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
}
const card = (t, body, note) => `<section class="card"><h3>${t}</h3>${note ? `<p class="note">${note}</p>` : ""}${body}</section>`;
const colorOf = (list, k) => PAL[list.indexOf(k) % PAL.length];

/* ---------- views ---------- */
function vOverview() {
  const rs = rows(), prod = sum(rs, 4), area = sum(rs, 5), ds = districts();
  const cc = D.corr_crop.slice().sort((a, b) => b.pearson_r - a.pearson_r), dry = D.extreme.filter(e => e.cls.startsWith("Deficient"));
  const dryAvg = dry.reduce((a, e) => a + e.mean_yield_change_pct, 0) / (dry.length || 1), tr = { Increasing: 0, Decreasing: 0 };
  D.districts.forEach(d => { if (tr[d.trend] != null) tr[d.trend]++; });
  const t = D.districts.slice().sort((a, b) => b.pearson_r - a.pearson_r)[0], sm = PR.regression.find(r => r.selected), k = [["Total production", fmt(prod) + " t"], ["Cropped area", fmt(area) + " ha"], ["Average yield", (prod / (area || 1)).toFixed(2) + " t/ha"],
    ["Districts", ds.length], ["Rain–yield correlation", D.overall_r.toFixed(2)], ["ML yield error (unseen years)", sm.mape.toFixed(1) + "%"]];
  const ins = [];
  if (cc.length) ins.push(`<b>${esc(cc[0].crop)}</b> is the most rainfall-sensitive crop (r = ${cc[0].pearson_r.toFixed(2)}); <b>${esc(cc[cc.length - 1].crop)}</b> is the least (r = ${cc[cc.length - 1].pearson_r.toFixed(2)}).`);
  ins.push(`In deficient-rainfall years (anomaly below −1σ), yields fall by <b>${Math.abs(dryAvg).toFixed(1)}%</b> on average across crops.`);
  if (t) ins.push(`District whose yields follow rainfall most closely: <b>${esc(t.district)}, ${esc(t.state)}</b> (r = ${t.pearson_r.toFixed(2)}, ${t.sensitivity_pct_per_sigma.toFixed(1)}% yield change per 1σ of rainfall).`);
  ins.push(`Machine learning: the <b>${esc(PR.meta.best)}</b> model predicts yield on unseen years with ~${sm.mape.toFixed(1)}% error — see the Prediction tab.`);
  ins.push(`Rainfall trends: ${tr.Increasing} districts significantly wetter, ${tr.Decreasing} drier, the rest without a significant trend.`);
  return `<div class="kpis">${k.map(([a, b]) => `<div class="kpi"><span>${a}</span><b>${b}</b></div>`).join("")}</div>` +
    card("Key insights", `<ul class="insights">${ins.map(i => `<li>${i}</li>`).join("")}</ul>`) +
    `<div class="grid2">${card("Production by season", barH(top(sumBy(rs, r => r[2]), 8)))}${card("Top states by production", barH(top(sumBy(rs, r => r[0]), 10)))}</div>`;
}

function vProduction() {
  const ix = { state: 0, crop: 1, season: 2 }[S.by], rs = rows(), gm = new Map();
  rs.forEach(r => { if (!gm.has(r[ix])) gm.set(r[ix], new Map()); const m = gm.get(r[ix]); m.set(r[3], (m.get(r[3]) || 0) + r[4]); });
  const seg = `<div class="seg">${["state", "crop", "season"].map(b => `<button data-by="${b}" class="${S.by === b ? "on" : ""}">By ${b}</button>`).join("")}</div>`;
  return card("Crop production over time", seg + lineChart([...gm].map(([name, m]) => ({ name, pts: [...m] })), { yfmt: fmt }), "Total production (tonnes) per year for the selected filters.") +
    `<div class="grid2">${card("Production by crop", barH(top(sumBy(rs, r => r[1]), 10)))}${card("Share of area by season", barH(top(sumBy(rs.map(r => [r[0], r[1], r[2], r[3], r[5], 0]), r => r[2]), 8), { fmtv: fmt }))}</div>`;
}

const cap = t => t.charAt(0) + t.slice(1).toLowerCase();
function vRainfall() {
  const st = D.filters.states.filter(s => S.state === "All" || s === S.state), filtered = S.crop !== "All" || S.season !== "All";
  const okc = r => (S.crop === "All" || r[1] === S.crop) && (S.season === "All" || r[2] === S.season);
  // is this crop grown in this season (in the chosen state) at all?
  const avail = !filtered || D.grow.some(g => (S.state === "All" || g[0] === S.state) && (S.crop === "All" || g[2] === S.crop) && (S.season === "All" || g[3] === S.season));
  let ann;
  if (!filtered) ann = st.map(s => ({ name: s, pts: D.rain_state_year.filter(r => r[0] === s && r[1] >= S.y0 && r[1] <= S.y1).map(r => [r[1], r[2]]) }));
  else {   // season rainfall over the districts that grow the selected crop / season
    const m = new Map();
    D.rain_crop_season.forEach(r => { if ((S.state === "All" || r[0] === S.state) && okc(r) && r[3] >= S.y0 && r[3] <= S.y1) {
      const k = r[0] + "|" + r[3], a = m.get(k) || [0, 0]; a[0] += r[4]; a[1]++; m.set(k, a); } });
    ann = st.map(s => ({ name: s, pts: [...m].filter(([k]) => k.startsWith(s + "|")).map(([k, a]) => [+k.split("|")[1], a[0] / a[1]]) }));
  }
  const ml = S.season === "All" ? D.months : D.season_months[S.season] || D.months;      // months shown, in season order
  const mon = !avail ? [] : st.map(s => { const arr = S.crop === "All" ? D.rain_monthly[s] : D.rain_monthly_crop[s + "|" + S.crop];
    return arr && { name: s, pts: ml.map((m, j) => [j + 1, arr[D.months.indexOf(m)]]).filter(p => p[1] != null) }; }).filter(Boolean);
  const okd = new Set(D.grow.filter(g => (S.crop === "All" || g[2] === S.crop) && (S.season === "All" || g[3] === S.season)).map(g => g[0] + "|" + g[1]));
  const cnt = {}; districts().filter(d => okd.has(d.state + "|" + d.district)).forEach(d => cnt[d.trend] = (cnt[d.trend] || 0) + 1);
  const cl = { Increasing: "#1565c0", Decreasing: "#ef6c00", "No significant trend": "#90a4ae" };
  const what = (S.crop === "All" ? "all crops" : S.crop) + (S.season === "All" ? "" : ", " + cap(S.season));
  const title = filtered ? `${S.season === "All" ? "Season" : cap(S.season)} rainfall trend – ${S.crop === "All" ? "all crops" : S.crop}` : "Annual rainfall trend";
  const note = filtered ? `Mean season rainfall (mm) over the districts that grow the selected crop${S.season === "All" ? "" : " (" + ml.map(m => m[0] + m.slice(1).toLowerCase()).join(", ") + ")"}.` : "Mean annual rainfall per state (mm).";
  return card(title, avail ? lineChart(ann, { yfmt: v => Math.round(v) + " mm" }) : empty(), note) +
    `<div class="grid2">${card("Monthly rainfall profile", lineChart(mon, { yfmt: v => Math.round(v) + " mm", xfmt: i => ml[i - 1] }), filtered ? `Average monthly rainfall for ${what}${S.season === "All" ? "" : " – only the months of that season"}.` : "Average rainfall by month – shows monsoon vs winter-rain regimes.")}` +
    `${card("District rainfall trends", barH(Object.entries(cnt).map(([label, value]) => ({ label, value, color: cl[label] })), { fmtv: v => v + " districts" }), "Linear regression of annual rainfall on year (p < 0.1 counted as a trend)." + (filtered ? " Only districts growing the selected crop / season." : ""))}</div>`;
}

function distTable() {
  const q = S.q.toLowerCase(), ds = districts().filter(d => !q || (d.district + d.state).toLowerCase().includes(q));
  return table("dist", [{ k: "district", label: "District" }, { k: "state", label: "State" }, { k: "mean_annual_rain", label: "Rain (mm)", f: v => Math.round(v) },
    { k: "rain_cv", label: "Rain CV", f: v => (v * 100).toFixed(1) + "%" }, { k: "trend", label: "Trend" }, { k: "pearson_r", label: "r (rain↔yield)", f: v => v.toFixed(2) },
    { k: "sensitivity_pct_per_sigma", label: "%Δyield / 1σ", f: v => v.toFixed(1) },
    { k: "mean_annual_production", label: "Mean production (t)", f: v => fmt(v) }], ds, { k: "mean_annual_production", d: -1 });
}
function vDistricts() {
  const ds = districts(), keys = Object.keys(D.district_year).filter(k => S.state === "All" || k.startsWith(S.state + "|"));
  if (!keys.includes(S.dist)) S.dist = keys[0];
  const dy = (D.district_year[S.dist] || []).filter(r => r[0] >= S.y0 && r[0] <= S.y1);
  const opts = keys.map(k => `<option value="${esc(k)}"${k === S.dist ? " selected" : ""}>${esc(k.replace("|", " – "))}</option>`).join("");
  return card("District comparison – top 10 by mean annual production", barH(ds.slice().sort((a, b) => b.mean_annual_production - a.mean_annual_production).slice(0, 10).map(d => ({ label: d.district + " (" + d.state + ")", value: d.mean_annual_production, color: colorOf(D.filters.states, d.state) })), { lw: 200 })) +
    card("District drill-down", `<label class="note">District <select id="dsel">${opts}</select></label><div class="grid2"><div>${lineChart([{ name: "Production", pts: dy.filter(r => r[1] != null).map(r => [r[0], r[1]]) }])}</div><div>${lineChart([{ name: "Annual rainfall", color: "#1565c0", pts: dy.filter(r => r[2] != null).map(r => [r[0], r[2]]) }], { yfmt: v => Math.round(v) + " mm" })}</div></div>`, "Left: total crop production (t). Right: annual rainfall (mm).") +
    card("All districts", `<input id="q" type="search" placeholder="Search district or state…" value="${esc(S.q)}"><div id="dtable" style="margin-top:10px">${distTable()}</div>`, "Click a column header to sort.");
}

/* ---------- prediction ---------- */
const PR = D.pred;
S.p = { state: null, dist: null, key: null, year: null, rain: null, area: null };
const [Z0, Z1, DZ] = PR.meta.z_grid;
const normCdf = x => { // Abramowitz-Stegun 7.1.26, |error| < 1.5e-7
  const t = 1 / (1 + 0.3275911 * Math.abs(x) / Math.SQRT2), y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x / 2);
  return x >= 0 ? 0.5 * (1 + y) : 0.5 * (1 - y); };
const yf = v => (v >= 100 ? v.toFixed(1) : v >= 10 ? v.toFixed(2) : v.toFixed(3));
function predSel() {
  const cs = PR.combos, P = S.p, states = [...new Set(cs.map(c => c.state))].sort();
  if (!states.includes(P.state)) P.state = states[0];
  const dists = [...new Set(cs.filter(c => c.state === P.state).map(c => c.district))].sort();
  if (!dists.includes(P.dist)) P.dist = dists[0];
  const opts = cs.filter(c => c.state === P.state && c.district === P.dist);
  let c = opts.find(o => o.key === P.key); if (!c) { c = opts[0]; P.key = c.key; P.rain = null; P.area = null; }
  if (!PR.meta.years.includes(P.year)) P.year = PR.meta.forecast_year;
  return { states, dists, opts, c };
}
/* model output for an exact year + rainfall value: linear interpolation between the fitted model's 0.1σ grid points */
function predict(c, year, rain, area) {
  const yi = PR.meta.years.indexOf(year), grid = c.grid[yi];
  const zRaw = (rain - c.rain_mean) / c.rain_std, z = Math.min(Math.max(zRaw, Z0), Z1), pos = (z - Z0) / DZ, i = Math.min(Math.floor(pos), grid.length - 2), t = pos - i;
  const y = grid[i] + t * (grid[i + 1] - grid[i]), yN = grid[Math.round(-Z0 / DZ)];
  const h = year - PR.meta.last_data_year, sigma = c.sigma * Math.sqrt(1 + Math.max(PR.meta.horizon_k, 0) * (h - 1)), k = PR.meta.pi_z * sigma;
  const mu = Math.log(y / c.base), pL = normCdf((Math.log(PR.meta.low) - mu) / sigma), pH = 1 - normCdf((Math.log(PR.meta.high) - mu) / sigma), p = [pL, Math.max(1 - pL - pH, 0), pH];
  return { z: zRaw, clamped: zRaw !== z, y, lo: y * Math.exp(-k), hi: y * Math.exp(k), vsAvg: (y / c.base - 1) * 100, vsNormal: (y / yN - 1) * 100, yN, p, horizon: h,
    cls: CLS[p.indexOf(Math.max(...p))], prod: area == null ? null : y * area, prodLo: area == null ? null : y * Math.exp(-k) * area, prodHi: area == null ? null : y * Math.exp(k) * area };
}
const CLS = ["Low", "Normal", "High"], CCOL = { Low: "#c62828", Normal: "#78909c", High: "#2e7d32" };
const rainVal = c => S.p.rain == null ? Math.round(c.rain_mean) : S.p.rain, areaVal = c => S.p.area == null ? Math.round(c.area) : S.p.area;

function predOut() {
  const { c } = predSel(), rain = rainVal(c), area = areaVal(c), year = S.p.year;
  const r = predict(c, year, rain, area), rg = `${Math.round(c.rain_min)}–${Math.round(c.rain_max)} mm`;
  const warn = r.clamped ? `Rainfall is ${Math.abs(r.z).toFixed(1)}σ from normal – beyond the modelled ±${Z1}σ, so the prediction is held at the ±${Z1}σ value.`
    : (rain < c.rain_min || rain > c.rain_max) ? `Outside the ${rg} seen in the historical data – treat this as an extrapolation.` : "";
  const k = [["Predicted yield", `${yf(r.y)} t/ha`], [`${Math.round(PR.meta.pi_level * 100)}% prediction range`, `${yf(r.lo)} – ${yf(r.hi)}`],
    ["Expected production", r.prod == null ? "–" : `${fmt(r.prod)} t`],
    ["vs long-run average", `${r.vsAvg >= 0 ? "+" : ""}${r.vsAvg.toFixed(1)}%`],
    ["Likely outcome", `<span class="outcome"><span class="chip" style="background:${CCOL[r.cls]}">${r.cls}</span><span class="pct">${Math.round(Math.max(...r.p) * 100)}%</span></span>`]];
  return (warn ? `<p class="warn">${warn}</p>` : "") +
    `<div class="kpis">${k.map(([a, b]) => `<div class="kpi"><span>${a}</span><b style="font-size:${a === "Predicted yield" ? 26 : 20}px">${b}</b></div>`).join("")}</div>` +
    `<p class="note">For ${year} (${r.horizon} year${r.horizon === 1 ? "" : "s"} beyond the data), ${Math.round(rain)} mm is ${r.z >= 0 ? "+" : ""}${r.z.toFixed(2)}σ (${((rain / c.rain_mean - 1) * 100).toFixed(0)}%) versus this district's normal of ${Math.round(c.rain_mean)} mm. ` +
    `At normal rainfall the model predicts ${yf(r.yN)} t/ha, so this rainfall changes the yield by <b>${r.vsNormal >= 0 ? "+" : ""}${r.vsNormal.toFixed(1)}%</b>. ` +
    `Outcome probabilities: Low ${(r.p[0] * 100).toFixed(0)}% · Normal ${(r.p[1] * 100).toFixed(0)}% · High ${(r.p[2] * 100).toFixed(0)}%.</p>`;
}

function vPrediction() {
  const m = PR.meta, sel0 = PR.regression.find(r => r.selected), lin = PR.regression.find(r => !r.selected), oc = PR.classification[0];
  const { states, dists, opts, c } = predSel(), pct0 = v => Math.round(v * 100) + "%";
  const sel = (id, lab, list, cur) => `<label>${lab} <select id="${id}">${list.map(x => `<option value="${esc(x.v ?? x)}"${(x.v ?? x) === cur ? " selected" : ""}>${esc(x.t ?? x)}</option>`).join("")}</select></label>`;
  const k = [["Yield error on unseen years", sel0.mape.toFixed(1) + "%", `mean absolute error, test years ${m.test_years[0]}–${m.test_years[1]}`], ["R² (relative yield)", sel0.r2.toFixed(2), "share of variation explained on unseen years"],
    [`${pct0(m.pi_level)} range hit rate`, pct0(m.coverage), `share of true yields inside the range`], ["Outcome accuracy", pct0(oc.accuracy), "Low / Normal / High called correctly"]];
  const form = `<div class="filters" style="position:static;border:1px solid var(--line);border-radius:10px;margin-bottom:12px">` +
    sel("pst", "State", states, S.p.state) + sel("pdi", "District", dists, S.p.dist) + sel("pcr", "Crop (season)", opts.map(o => ({ v: o.key, t: o.crop + " (" + o.season.toLowerCase() + ")" })), S.p.key) +
    sel("pyr", "Forecast year", m.years, S.p.year) +
    `<label>Season rainfall (mm)<input id="prain" type="number" min="0" step="any" value="${rainVal(c)}" inputmode="decimal"></label>` +
    `<label>Cropped area (ha)<input id="parea" type="number" min="0" step="any" value="${areaVal(c)}" inputmode="decimal"></label>` +
    `<button type="button" id="prst">Use normal rainfall</button></div>` +
    `<p class="note" style="margin-top:-4px">Type the exact rainfall you expect for the season and pick any year up to ${m.years[m.years.length - 1]}. Normal for this district: <b>${Math.round(c.rain_mean)} mm</b> · seen in ${m.train_years[0]}–${m.test_years[1]}: ${Math.round(c.rain_min)}–${Math.round(c.rain_max)} mm. ` +
    `Predictions were checked against real unseen years up to ${m.tested_horizon} years ahead; further out the prediction range widens to reflect the extra uncertainty. Area defaults to the average of the last 3 years.</p>`;
  const FEAT_LABEL = { rain_z: "rainfall anomaly", rain_z_sq: "rainfall anomaly²", rain_anom_pct_f: "rainfall anomaly %",
    annual_rain: "annual rainfall", rain_cv: "rainfall variability", yr_c: "year", season_rain: "season rainfall" };
  const imp = m.importance.slice(0, 4).map(([n]) => FEAT_LABEL[n] || n).join(", ");
  return `<div class="kpis">${k.map(([a, b, n]) => `<div class="kpi"><span>${a}</span><b>${b}</b><span>${n}</span></div>`).join("")}</div>` +
    card(`Predict crop yield (2016–${m.years[m.years.length - 1]})`, form + `<div id="predOut">${predOut()}</div>`,
      `Model: <b>${esc(m.best)}</b> (${m.n_estimators} trees, min ${m.min_samples_leaf} samples/leaf — tuned on a validation window inside the training years), ` +
      `beating a Linear Regression baseline (${lin.mape.toFixed(2)}% error). ` +
      `Top drivers by feature importance: ${imp}. Inputs: state, district, crop, season, year and rainfall. Outcome is measured against the district-crop's long-run average yield (Low &lt; ${pct0(m.low)} · Normal · High &gt; ${pct0(m.high)}).`);
}

/* ---------- wiring ---------- */
const V = { overview: vOverview, production: vProduction, rainfall: vRainfall, districts: vDistricts, prediction: vPrediction };
function render() {
  let html;
  try { html = V[S.tab](); }
  catch (err) {
    console.error("Render failed for tab", S.tab, err);
    html = `<div class="card"><h3>Something went wrong showing this tab</h3><p class="note">Try a hard refresh (Ctrl/Cmd+Shift+R). If it persists, open the browser console and check the error, or click Reset.</p><p class="note">${esc(err && err.message || err)}</p></div>`;
  }
  $("#view").innerHTML = html;
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("on", b.dataset.tab === S.tab));
  $("#filters").hidden = S.tab === "prediction";
}
function fill(id, list, val) { $(id).innerHTML = list.map(v => `<option${String(v) === String(val) ? " selected" : ""}>${esc(v)}</option>`).join(""); }
function initFilters() {
  const yrs = Array.from({ length: YMAX - YMIN + 1 }, (_, i) => YMIN + i);
  fill("#fState", ["All", ...D.filters.states], S.state); fill("#fCrop", ["All", ...D.filters.crops], S.crop); fill("#fSeason", ["All", ...D.filters.seasons], S.season);
  fill("#fY0", yrs, S.y0); fill("#fY1", yrs, S.y1);
}
$("#nav").addEventListener("click", e => { const t = e.target.dataset && e.target.dataset.tab; if (t) { S.tab = t; render(); } });
function applyFilters() {
  S.state = $("#fState").value; S.crop = $("#fCrop").value; S.season = $("#fSeason").value; S.y0 = +$("#fY0").value; S.y1 = +$("#fY1").value;
  render();
}
// Filters now apply as soon as a dropdown changes (the Apply button still works). An inverted year range is fixed first.
$("#filters").addEventListener("change", e => {
  let y0 = +$("#fY0").value, y1 = +$("#fY1").value;
  if (y0 > y1) { if (e.target.id === "fY0") y1 = y0; else y0 = y1; $("#fY0").value = y0; $("#fY1").value = y1; }
  applyFilters();
});
$("#apply").addEventListener("click", applyFilters);
$("#reset").addEventListener("click", () => { Object.assign(S, { state: "All", crop: "All", season: "All", y0: YMIN, y1: YMAX, q: "" }); initFilters(); render(); });
const view = $("#view");
view.addEventListener("click", e => {
  const t = e.target.closest && e.target.closest("[data-sort]"), b = e.target.closest && e.target.closest("[data-by]");
  if (e.target.id === "prst") { S.p.rain = null; render(); return; }
  if (t) { const [id, k] = t.dataset.sort.split(":"), cur = S.sort[id] || {}; S.sort[id] = { k, d: cur.k === k ? -cur.d : (k === "district" || k === "state" || k === "crop" || k === "job" ? 1 : -1) }; render(); }
  else if (b) { S.by = b.dataset.by; render(); }
});
view.addEventListener("change", e => {
  if (e.target.id === "dsel") { S.dist = e.target.value; render(); }
  if (e.target.id === "pst") { S.p.state = e.target.value; S.p.dist = null; S.p.key = null; S.p.rain = null; S.p.area = null; render(); }
  if (e.target.id === "pdi") { S.p.dist = e.target.value; S.p.key = null; S.p.rain = null; S.p.area = null; render(); }
  if (e.target.id === "pcr") { S.p.key = e.target.value; S.p.rain = null; S.p.area = null; render(); }
  if (e.target.id === "pyr") { S.p.year = Number(e.target.value); $("#predOut").innerHTML = predOut(); }
});
view.addEventListener("input", e => {
  if (e.target.id === "prain" || e.target.id === "parea") {   // exact typed values; empty / invalid input shows a hint instead of a prediction
    const v = e.target.value.trim() === "" ? NaN : Number(e.target.value), ok = Number.isFinite(v) && v >= 0;
    if (ok) { S.p[e.target.id === "prain" ? "rain" : "area"] = v; $("#predOut").innerHTML = predOut(); }
    else $("#predOut").innerHTML = `<p class="warn">Enter a number (0 or more) in the ${e.target.id === "prain" ? "rainfall" : "area"} field.</p>`;
  }
  if (e.target.id === "q") { S.q = e.target.value; $("#dtable").innerHTML = distTable(); } });

$("#foot").textContent = `Data generated ${D.meta.generated_at} · Pipeline: clean → integrate → analytics + machine learning → dashboard`;
initFilters(); render();
window.__app = { S, render, tabs: Object.keys(V) };
})();
