/* Reports: the org report, release readiness for one product version, one feature's report, and the empty and loading states.
   The data is data/reports.js; the level, the period, the release and every row are links the server answers. */
import { I, st, ver, actor, bar, legend, dd, dr, tipA, pinTip, crumbs, esc } from "../ui.js";
import { href } from "../shell.js";

const sum = (c) => Object.values(c).reduce((a, b) => a + b, 0);
/* success rate = success / results that ran (untested excluded) */
const pct = (c) => Math.round(((c.success || 0) / Math.max(1, sum(c) - (c.untested || 0))) * 100);
/* a percentage the API may not have (null: nothing ran) */
const pc = (v) => (v === null || v === undefined ? "–" : `${v}%`);
/* the period in every link: ?range= (and from/to for a custom one) */
const pk = (d) => d.periodKeep || {};
const at = (d, over) => href("reports", { ...pk(d), product: d.product ? d.product.key : undefined, ...over });
const LEVELS = [["org", "Org"], ["product", "Product"], ["feature", "Feature"]];
const level = (on) => `<div class="seg" role="tablist" aria-label="Report level">${LEVELS.map(([h, l]) => `<button class="${h === on ? "on" : ""}" data-level="${h}">${l}</button>`).join("")}</div>`;
/* dr() takes Dates for a custom range; the adapter gives ISO days */
const drOf = (p = {}) => (p.from ? Object.assign({}, p, { from: date(p.from), to: date(p.to) }) : p);
const head = (crumbs, eyebrow, h1, on, period = {}) => `<div class="crumbs">${crumbs}</div>
<div class="eyebrow">${eyebrow}</div>
<div class="ph" style="margin-top:6px"><h1>${h1}</h1><div class="rp-tools">${level(on)}${dr(Object.assign({ value: "30d" }, drOf(period)))}</div></div>
<p class="sub" style="margin-top:-10px;margin-bottom:22px">Results count only against the case_version pinned in each cycle.</p>`;
const kpis = (k) => `<div class="kpis">${k.map(([l, v, d]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div>${d ? `<div class="d">${d}</div>` : ""}</div>`).join("")}</div>`;
const sep = '<span class="sep">/</span>';
const date = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
const mday = (iso) => date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const results = (n) => (n === 1 ? "result" : "results");

/* org */
const KINDS = ["success", "fail", "error", "skip"];
const chart = (days) => {
  /* the scale: 80 results a day, or the busiest day when it had more */
  const max = Math.max(80, ...days.map((x) => KINDS.reduce((n, k) => n + (x[k] || 0), 0)));
  const last = days.length - 1;
  return `<div class="chart" role="img" aria-label="Results per day, last ${days.length} days">${[25, 50, 75].map((p) => `<span class="gl" style="bottom:${p}%"></span>`).join("")}${days.map((x, i) => `<div class="col${i === last ? " now" : ""}"${tipA(mday(x.date), KINDS.map((k) => [k, `var(--st-${k})`, x[k]]), ["Results", x.success + x.fail + x.error + x.skip])}>${KINDS.map((k) => x[k] ? `<i class="${k}" style="height:${(x[k] / max) * 100}%"></i>` : "").join("")}</div>`).join("")}</div>
  <div class="chart-x">${days.map((x, i) => `<span>${i === 0 || i === last ? mday(x.date) : i % 2 === 0 ? date(x.date).getDate() : ""}</span>`).join("")}</div>`;
};
const orgBody = (d) => {
  const k = d.org.kpis, t = d.org.trend, P = d.org.products;
  const go = (p) => at(d, { level: "product", product: p.key });
  return kpis([["Ready cases", k.readyCases, `across ${k.products} products`], ["Success rate", pc(k.successPct), "of results that ran"], ["Automated", pc(k.automatedPct), "automation = automated"],["Open cycles", k.openCycles, `${st("untested", { label: `${k.untested} untested` })}`]]) +
  `<div class="card" style="margin-bottom:20px"><div class="hd"><span class="eyebrow">Trend</span>Results per day<span class="r">${legend(t.totals).replace(/<span style="--c:var\(--st-(ignore|cancel|untested)\)">[^<]*<b>0<\/b><\/span>/g, "")}</span></div><div class="bd"><div class="trend"><div style="min-width:0">${chart(t.days)}</div>
  <div class="side-stats"><div><div class="l">Results</div><div class="v">${t.results}</div></div><div><div class="l">Peak day</div><div class="v">${esc(t.peakDay)}</div></div><div><div class="l">By agents</div><div class="v">${pc(t.byAgentsPct)}</div></div></div></div></div></div>` +
  `<div class="card"><div class="hd"><span class="eyebrow">Products</span>By product</div><div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Product</th><th class="num">Cases</th><th class="num">Automated</th><th style="min-width:200px">Results, ${esc(d.periodLabel || "last 30 days")}</th><th class="num">Success rate</th><th class="num">Open cycles</th></tr></thead><tbody>` +
  P.map((p) => `<tr><td><a href="${go(p)}"><span class="key">${esc(p.key)}</span> <span class="ell" style="display:inline-block;max-width:280px;vertical-align:bottom">${esc(p.name)}</span></a></td><td class="num">${p.cases}</td><td class="num">${pc(p.automatedPct)}</td><td>${sum(p.results) ? bar(p.results) : '<span class="faint">no results yet</span>'}</td><td class="num">${sum(p.results) ? pct(p.results) + "%" : "–"}</td><td class="num">${p.openCycles}</td></tr>`).join("") +
  `</tbody></table></div><div class="mlist">` + P.map((p) => `<div class="it"><div class="row"><span class="key">${esc(p.key)}</span><a href="${go(p)}" class="ell" style="flex:1">${esc(p.name)}</a><b>${sum(p.results) ? pct(p.results) + "%" : "–"}</b></div>${sum(p.results) ? bar(p.results) : '<span class="faint" style="font-size:12px">no results yet</span>'}<span class="muted" style="font-size:12px">${p.cases} cases · ${pc(p.automatedPct)} automated · ${p.openCycles} open cycles</span></div>`).join("") + `</div></div><div style="margin-top:14px">${legend()}</div>`;
};
const orgHead = (d, period) => head(crumbs([["Insights"], ["Reports"]]).slice(20, -6), "Org report", esc(d.ctx.org.name), "org", period);
const org = (d) => orgHead(d, d.period) + orgBody(d);

/* product: release readiness */
const GROUPS = [["in_progress", "In progress", "var(--retest)"], ["planned", "Planned", "var(--muted)"], ["released", "Released", "var(--pass)"]];
const releaseOptions = (r) => [
  ...GROUPS.flatMap(([s, g, dot]) => [{ group: g }, ...r.releases.filter((x) => x.status === s).map((x) => ({ v: x.ver, label: `${x.ver} · ${x.name}`, short: x.ver === r.ver ? `${x.ver} · ${x.name}${x.due ? " · due " + x.due : ""}` : undefined, hint: x.hint, dot }))]),
  "-",
  { v: "none", label: "No release (whole product)", hint: "every cycle in the period", icon: I.report }
];
const verdict = (v) => `<span class="pill ${{ "ready": "ready", "at risk": "expiring", "in progress": "in_progress", "not started": "draft" }[v]}">${v}</span>`;
const orgLink = (d) => `<a href="${at(d, { level: "org" })}">${esc(d.ctx.org.name)}</a>`;
const productLabel = (p) => esc(`${p.key} · ${p.name}`);
const productHref = (p) => href("products", { id: p.key, product: p.key });
/* the release a link keeps: its id, or "none" for the whole product */
const relOf = (r) => r.id || "none";
const product = (d) => {
  const p = d.product, r = d.release, k = r.kpis, x = r.driftExample;
  const verCrumb = r.id ? `<a href="${href("releases", { product: p.key, id: r.id })}">version ${esc(r.ver)}</a>` : "<span>whole product</span>";
  const feat = (f) => at(d, { level: "feature", feature: f.id, release: relOf(r) });
  return head(`${orgLink(d)}${sep}<a href="${productHref(p)}">${productLabel(p)}</a>${sep}${verCrumb}${sep}<span>Readiness</span>`, "Release readiness", `${esc(p.name)} · ${r.id ? `release ${esc(r.ver)}` : "whole product"}`, "product", d.period) +
  `<div class="rel-pick"><span class="mini-lbl" style="margin:0">Release</span>${dd({ value: r.id ? r.ver : "none", options: releaseOptions(r), cls: "block", search: "Find a release", open: !!r.open, label: "Release", name: "release" })}</div>` +
  kpis([["In affected features", k.cases, "cases"], ["Ran", `${k.ran} of ${k.cases}`, `${k.ranPct}% have a result`], ["Fail · error", `${k.fail} · ${k.error}`, `${st("skip", { label: `${k.skip} skip` })}`], ["Version drift", k.drift, `${results(k.drift)} on an older case_version`]]) +
  `<div class="card"><div class="hd"><span class="eyebrow">Features</span>Per affected feature<span class="r faint" style="font-size:12px">${r.id ? `from ${r.cycles} release cycles` : "every cycle in the period"} · pinned versions</span></div><div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Feature</th><th class="num">Cases</th><th style="min-width:200px">Latest result per case</th><th>Version drift</th><th>Readiness</th></tr></thead><tbody>` +
  r.features.map((f) => `<tr><td><a href="${feat(f)}">${esc(f.path)}</a></td><td class="num">${f.cases}</td><td>${bar(f.results)}</td><td>${f.drift ? `<span class="drift">${I.warn}<span>${esc(f.driftNote)}</span></span>` : '<span class="faint">none</span>'}</td><td>${verdict(f.readiness)}</td></tr>`).join("") +
  `</tbody></table></div><div class="mlist">` + r.features.map((f) => `<div class="it"><div class="row"><a href="${feat(f)}" class="ell" style="flex:1">${esc(f.path)}</a>${verdict(f.readiness)}</div>${bar(f.results)}<span class="muted" style="font-size:12px">${f.cases} cases${f.drift ? " · " + esc(f.driftNote) : ""}</span></div>`).join("") +
  `</div></div><div style="margin-top:14px">${legend(r.latest)}</div>
  <div class="banner info" style="margin-top:20px">${I.info}<div><b>Version drift</b>: a result counts for the case_version it ran against. When a case changed after its result${x ? ` (e.g. ${esc(x.key)} ${ver(x.from, 1)} → ${ver(x.to)})` : ""}, the feature shows <b>at risk</b> until it is re-run as a new attempt or the owner accepts the older result.</div></div>`;
};

/* feature */
const note = (c) => c.noteKind === "issue" ? `<a class="key"${c.noteHref ? ` href="${esc(c.noteHref)}" target="_blank" rel="noopener"` : ""}>${esc(c.note)}</a>` : c.noteKind === "attempt" ? `<span class="chip acc">${esc(c.note)}</span>` : esc(c.note);
const feature = (d) => {
  const p = d.product, r = d.release, f = d.feature, k = f.kpis, o = k.results;
  const verCrumb = `<a href="${at(d, { level: "product", release: relOf(r) })}">${r.id ? `version ${esc(r.ver)}` : "whole product"}</a>`;
  return head(`${orgLink(d)}${sep}<a href="${productHref(p)}">${productLabel(p)}</a>${sep}${verCrumb}${sep}<a href="${href("tree", { product: p.key, feature: f.id })}">${esc(f.path)}</a>`, "Feature report", esc(f.name), "feature", d.period) +
  kpis([["Cases", k.cases, bar(o)], ["Success", o.success, `${o.fail} fail · ${o.error} error · ${o.skip} skip · ${o.ignore} ignore`], ["Success rate", pc(k.successPct), `over the last ${f.history.length} runs`], ["Version drift", k.drift, `${results(k.drift)} on an older case_version`]]) +
  `<div class="card"><div class="hd"><span class="eyebrow">Cases</span>${r.id ? `Latest result in ${esc(r.ver)} cycles` : `Latest result, ${esc(d.periodLabel || "last 30 days")}`}</div><div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Case</th><th>Ran on</th><th>Result</th><th>By</th><th class="hide-m">When</th><th class="hide-m">Note</th></tr></thead><tbody>` +
  f.cases.map((c) => `<tr><td><a href="${href("case", { product: p.key, id: c.id })}" class="key">${esc(c.key)}</a> <span class="ell" style="display:inline-block;max-width:340px;vertical-align:bottom" title="${esc(c.title)}">${esc(c.title)}</span></td><td>${ver(c.ranOn, 1)}${c.current > c.ranOn ? ` <span class="drift">current v${c.current}</span>` : ""}</td><td>${st(c.result)}${c.why ? `<span class="why">${esc(c.why)}</span>` : ""}</td><td>${c.by ? actor(c.by.kind, esc(c.by.id), { k: false }) : '<span class="faint">–</span>'}</td><td class="hide-m faint" style="font-size:12.5px">${esc(c.when || "–")}</td><td class="hide-m" style="font-size:12.5px">${note(c)}</td></tr>`).join("") +
  `</tbody></table></div><div class="mlist">` + f.cases.map((c) => `<div class="it"><div class="row"><span class="key">${esc(c.key)}</span>${ver(c.ranOn, 1)}${st(c.result)}</div><span class="ell" title="${esc(c.title)}">${esc(c.title)}</span>${c.why ? `<span class="why" style="margin:0">${esc(c.why)}</span>` : ""}${c.current > c.ranOn ? `<span class="drift">current is v${c.current}: run a new attempt</span>` : ""}</div>`).join("") +
  `</div></div>
  <div class="card" style="margin-top:20px"><div class="hd"><span class="eyebrow">History</span>Last ${f.history.length} runs of this feature</div><div class="bd stack">${f.history.map((h) => `<div class="runs-row"><span class="ell">${esc(`${h.ver} · ${h.env} · ${h.when}`)}</span>${bar(h.results)}<span class="num muted" style="text-align:right">${pct(h.results)}%</span></div>`).join("")}</div></div>`;
};

const empty = (d) => {
  const p = d.product;
  return head(`${orgLink(d)}${sep}<a href="${href("products")}">Products</a>${sep}<span>${productLabel(p)}</span>`, "Product report", esc(p.name), "product", d.period) +
  `<div class="card"><div class="empty"><div class="ill">${I.report}</div><h3>No results yet</h3><p style="margin:0">${esc(p.key)} has ${p.cases} cases but no cycle has recorded a result. Reports fill in once a cycle runs.</p><a class="btn primary" href="${href("cycles", { product: p.key }, "new-cycle")}">${I.plus}New cycle</a></div></div>`;
};

const skel = () => `<div class="kpis" aria-busy="true">${[1, 2, 3, 4].map(() => `<div class="kpi"><span class="skel" style="width:40%"></span><span class="skel" style="height:24px;width:60%;margin-top:12px"></span></div>`).join("")}</div>
  <div class="card" style="margin-bottom:20px"><div class="hd"><span class="eyebrow">Trend</span>Results per day</div><div class="bd"><div class="chart">${[40, 62, 30, 18, 70, 66, 55, 60, 72, 35, 24, 80, 84, 68].map((h) => `<div class="col"><span class="skel" style="height:${h}%;border-radius:4px"></span></div>`).join("")}</div></div></div>
  <div class="card"><div class="hd"><span class="eyebrow">Products</span>By product</div><div class="bd stack">${[1, 2, 3, 4].map(() => `<span class="skel"></span>`).join("")}</div></div>`;

/* the period the date picker applied: a preset, else the two days picked on its calendars */
const pad = (n) => String(n).padStart(2, "0");
const isoOf = (dt) => `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
function picked(w) {
  const pre = w.querySelector(".dr-pre button.on");
  const now = new Date();
  const on = (y, m, dd) => isoOf(new Date(y, m, dd));
  if (pre) {
    const k = pre.dataset.pre;
    if (["today", "7d", "14d", "30d", "rel"].includes(k)) return { range: k };
    if (k === "y") return { range: "custom", from: on(now.getFullYear(), now.getMonth(), now.getDate() - 1), to: on(now.getFullYear(), now.getMonth(), now.getDate() - 1) };
    if (k === "m") return { range: "custom", from: on(now.getFullYear(), now.getMonth(), 1), to: isoOf(now) };
    if (k === "lm") return { range: "custom", from: on(now.getFullYear(), now.getMonth() - 1, 1), to: on(now.getFullYear(), now.getMonth(), 0) };
  }
  const cell = (el) => { const [y, m, dd] = el.dataset.day.split("-").map(Number); return on(y, m - 1, dd); };
  const a = w.querySelector(".cal-g .d.a"), b = w.querySelector(".cal-g .d.b") || a;
  return a ? { range: "custom", from: cell(a), to: cell(b) } : null;
}

/* live: the level switch, the period and the release picker are links the adapter loads again; wired on the
   document once, against the data of the last render */
let cur = null;
let wired = false;
const levelHref = (d, lv) => at(d, { level: lv, release: lv === "org" ? null : d.release ? relOf(d.release) : undefined, feature: lv === "feature" && d.feature ? d.feature.id : undefined });
const keepNow = (d) => ({ level: d.feature ? "feature" : d.release ? "product" : "org", release: d.release ? relOf(d.release) : undefined, feature: d.feature ? d.feature.id : undefined });
function wire() {
  if (wired) return;
  wired = true;
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest('[data-view="reports"] [data-level]');
    if (b && cur) location.assign(levelHref(cur, b.dataset.level));
  });
  document.addEventListener("dr:change", (e) => {
    const main = document.querySelector('[data-view="reports"]');
    if (!cur || !main) return;
    const to = e.detail.value === "custom" ? picked(main.querySelector("[data-drw]")) : { range: e.detail.value };
    if (to) location.assign(href("reports", { product: cur.product ? cur.product.key : undefined, ...keepNow(cur), range: null, from: null, to: null, ...to }));
  });
}
function after(main, state, d) {
  cur = d;
  wire();
  const rel = main.querySelector('.dd[data-name="release"]');
  if (rel) rel.addEventListener("dd:change", (e) => {
    const r = d.release.releases.find((x) => x.ver === e.detail.value);
    location.assign(at(d, { level: "product", release: r ? r.id : "none" }));
  });
}

export default { nav: "reports", default: "org", after, states: {
  "org": { render: org },
  "period-custom": { render: org, after: (m) => { const w = m.querySelector(".dr"); if (w) w.setAttribute("data-pinned", ""); } },
  "org-hover": { render: org, after: (m, d) => pinTip(m.querySelectorAll(".chart .col")[d.pinDay]) },
  "bar-hover": { render: product, after: (m) => { const b = [...m.querySelectorAll(".bar[data-tip]")].find((b) => b.getClientRects().length); if (b) b.scrollIntoView({ block: "center" }); pinTip(b); } },
  "product": { render: product },
  "pick-release": { render: product },
  "feature": { render: feature },
  "empty": { render: empty },
  "loading": { render: (d) => orgHead(d) + skel() }
}};
