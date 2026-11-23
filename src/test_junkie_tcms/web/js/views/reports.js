/* Reports: the org report, release readiness for one product version, one feature's report, and the empty and loading states. */
import { I, st, ver, actor, bar, legend, dd, dr, tipA, pinTip, crumbs, lnk, esc, toast } from "../ui.js";

const sum = (c) => Object.values(c).reduce((a, b) => a + b, 0);
/* success rate = success / results that ran (untested excluded) */
const pct = (c) => Math.round(((c.success || 0) / Math.max(1, sum(c) - (c.untested || 0))) * 100);
const LEVELS = [["org", "Org"], ["product", "Product"], ["feature", "Feature"]];
const level = (on) => `<div class="seg" role="tablist" aria-label="Report level">${LEVELS.map(([h, l]) => `<button class="${h === on ? "on" : ""}" data-level="${h}">${l}</button>`).join("")}</div>`;
const head = (crumbs, eyebrow, h1, on, period = {}) => `<div class="crumbs">${crumbs}</div>
<div class="eyebrow">${eyebrow}</div>
<div class="ph" style="margin-top:6px"><h1>${h1}</h1><div class="rp-tools">${level(on)}${dr(Object.assign({ value: "30d" }, period))}</div></div>
<p class="sub" style="margin-top:-10px;margin-bottom:22px">Results count only against the case_version pinned in each cycle.</p>`;
const kpis = (k) => `<div class="kpis">${k.map(([l, v, d]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div>${d ? `<div class="d">${d}</div>` : ""}</div>`).join("")}</div>`;
const sep = '<span class="sep">/</span>';
const date = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
const mday = (iso) => date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const results = (n) => (n === 1 ? "result" : "results");

/* org */
const KINDS = ["success", "fail", "error", "skip"];
const chart = (days) => {
  const max = 80;
  const last = days.length - 1;
  return `<div class="chart" role="img" aria-label="Results per day, last ${days.length} days">${[25, 50, 75].map((p) => `<span class="gl" style="bottom:${p}%"></span>`).join("")}${days.map((x, i) => `<div class="col${i === last ? " now" : ""}"${tipA(mday(x.date), KINDS.map((k) => [k, `var(--st-${k})`, x[k]]), ["Results", x.success + x.fail + x.error + x.skip])}>${KINDS.map((k) => x[k] ? `<i class="${k}" style="height:${(x[k] / max) * 100}%"></i>` : "").join("")}</div>`).join("")}</div>
  <div class="chart-x">${days.map((x, i) => `<span>${i === 0 || i === last ? mday(x.date) : i % 2 === 0 ? date(x.date).getDate() : ""}</span>`).join("")}</div>`;
};
const orgBody = (d) => {
  const k = d.org.kpis, t = d.org.trend, P = d.org.products;
  return kpis([["Ready cases", k.readyCases, `across ${k.products} products`], ["Success rate", `${k.successPct}%`, "of results that ran"], ["Automated", `${k.automatedPct}%`, "automation = automated"], ["Open cycles", k.openCycles, `${st("untested", { label: `${k.untested} untested` })}`]]) +
  `<div class="card" style="margin-bottom:20px"><div class="hd"><span class="eyebrow">Trend</span>Results per day<span class="r">${legend(t.totals).replace(/<span style="--c:var\(--st-(ignore|cancel|untested)\)">[^<]*<b>0<\/b><\/span>/g, "")}</span></div><div class="bd"><div class="trend"><div style="min-width:0">${chart(t.days)}</div>
  <div class="side-stats"><div><div class="l">Results</div><div class="v">${t.results}</div></div><div><div class="l">Peak day</div><div class="v">${esc(t.peakDay)}</div></div><div><div class="l">By agents</div><div class="v">${t.byAgentsPct}%</div></div></div></div></div></div>` +
  `<div class="card"><div class="hd"><span class="eyebrow">Products</span>By product</div><div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Product</th><th class="num">Cases</th><th class="num">Automated</th><th style="min-width:200px">Results, last 30 days</th><th class="num">Success rate</th><th class="num">Open cycles</th></tr></thead><tbody>` +
  P.map((p) => `<tr><td><a href="#product"><span class="key">${esc(p.key)}</span> <span class="ell" style="display:inline-block;max-width:280px;vertical-align:bottom">${esc(p.name)}</span></a></td><td class="num">${p.cases}</td><td class="num">${p.automatedPct}%</td><td>${sum(p.results) ? bar(p.results) : '<span class="faint">no results yet</span>'}</td><td class="num">${sum(p.results) ? pct(p.results) + "%" : "–"}</td><td class="num">${p.openCycles}</td></tr>`).join("") +
  `</tbody></table></div><div class="mlist">` + P.map((p) => `<div class="it"><div class="row"><span class="key">${esc(p.key)}</span><a href="#product" class="ell" style="flex:1">${esc(p.name)}</a><b>${sum(p.results) ? pct(p.results) + "%" : "–"}</b></div>${sum(p.results) ? bar(p.results) : '<span class="faint" style="font-size:12px">no results yet</span>'}<span class="muted" style="font-size:12px">${p.cases} cases · ${p.automatedPct}% automated · ${p.openCycles} open cycles</span></div>`).join("") + `</div></div><div style="margin-top:14px">${legend()}</div>`;
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
const orgLink = (d) => `<a href="#org">${esc(d.ctx.org.name)}</a>`;
const productLabel = (p) => esc(`${p.key} · ${p.name}`);
const product = (d) => {
  const p = d.product, r = d.release, k = r.kpis, x = r.driftExample;
  return head(`${orgLink(d)}${sep}<a href="${lnk("products.html")}">${productLabel(p)}</a>${sep}<a href="${lnk("releases.html#detail")}">version ${esc(r.ver)}</a>${sep}<span>Readiness</span>`, "Release readiness", `${esc(p.name)} · release ${esc(r.ver)}`, "product") +
  `<div class="rel-pick"><span class="mini-lbl" style="margin:0">Release</span>${dd({ value: r.ver, options: releaseOptions(r), cls: "block", search: "Find a release", open: !!r.open, label: "Release" })}</div>` +
  kpis([["In affected features", k.cases, "cases"], ["Ran", `${k.ran} of ${k.cases}`, `${k.ranPct}% have a result`], ["Fail · error", `${k.fail} · ${k.error}`, `${st("skip", { label: `${k.skip} skip` })}`], ["Version drift", k.drift, `${results(k.drift)} on an older case_version`]]) +
  `<div class="card"><div class="hd"><span class="eyebrow">Features</span>Per affected feature<span class="r faint" style="font-size:12px">from ${r.cycles} release cycles · pinned versions</span></div><div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Feature</th><th class="num">Cases</th><th style="min-width:200px">Latest result per case</th><th>Version drift</th><th>Readiness</th></tr></thead><tbody>` +
  r.features.map((f) => `<tr><td><a href="#feature">${esc(f.path)}</a></td><td class="num">${f.cases}</td><td>${bar(f.results)}</td><td>${f.drift ? `<span class="drift">${I.warn}<span>${esc(f.driftNote)}</span></span>` : '<span class="faint">none</span>'}</td><td>${verdict(f.readiness)}</td></tr>`).join("") +
  `</tbody></table></div><div class="mlist">` + r.features.map((f) => `<div class="it"><div class="row"><a href="#feature" class="ell" style="flex:1">${esc(f.path)}</a>${verdict(f.readiness)}</div>${bar(f.results)}<span class="muted" style="font-size:12px">${f.cases} cases${f.drift ? " · " + esc(f.driftNote) : ""}</span></div>`).join("") +
  `</div></div><div style="margin-top:14px">${legend(r.latest)}</div>
  <div class="banner info" style="margin-top:20px">${I.info}<div><b>Version drift</b>: a result counts for the case_version it ran against. When a case changed after its result (e.g. ${esc(x.key)} ${ver(x.from, 1)} → ${ver(x.to)}), the feature shows <b>at risk</b> until it is re-run as a new attempt or the owner accepts the older result.</div></div>`;
};

/* feature */
const note = (c) => c.noteKind === "issue" ? `<a class="key">${esc(c.note)}</a>` : c.noteKind === "attempt" ? `<span class="chip acc">${esc(c.note)}</span>` : esc(c.note);
const feature = (d) => {
  const p = d.product, r = d.release, f = d.feature, k = f.kpis, o = k.results;
  return head(`${orgLink(d)}${sep}<a href="${lnk("products.html")}">${productLabel(p)}</a>${sep}<a href="#product">version ${esc(r.ver)}</a>${sep}<a href="${lnk("tree.html")}">${esc(f.path)}</a>`, "Feature report", esc(f.name), "feature") +
  kpis([["Cases", k.cases, bar(o)], ["Success", o.success, `${o.fail} fail · ${o.error} error · ${o.skip} skip · ${o.ignore} ignore`], ["Success rate", `${k.successPct}%`, `over the last ${f.history.length} runs`], ["Version drift", k.drift, `${results(k.drift)} on an older case_version`]]) +
  `<div class="card"><div class="hd"><span class="eyebrow">Cases</span>Latest result in ${esc(r.ver)} cycles</div><div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Case</th><th>Ran on</th><th>Result</th><th>By</th><th class="hide-m">When</th><th class="hide-m">Note</th></tr></thead><tbody>` +
  f.cases.map((c) => `<tr><td><a href="${lnk("case.html")}" class="key">${esc(c.key)}</a> <span class="ell" style="display:inline-block;max-width:340px;vertical-align:bottom" title="${esc(c.title)}">${esc(c.title)}</span></td><td>${ver(c.ranOn, 1)}${c.current > c.ranOn ? ` <span class="drift">current v${c.current}</span>` : ""}</td><td>${st(c.result)}${c.why ? `<span class="why">${esc(c.why)}</span>` : ""}</td><td>${c.by ? actor(c.by.kind, c.by.id, { k: false }) : '<span class="faint">–</span>'}</td><td class="hide-m faint" style="font-size:12.5px">${esc(c.when || "–")}</td><td class="hide-m" style="font-size:12.5px">${note(c)}</td></tr>`).join("") +
  `</tbody></table></div><div class="mlist">` + f.cases.map((c) => `<div class="it"><div class="row"><span class="key">${esc(c.key)}</span>${ver(c.ranOn, 1)}${st(c.result)}</div><span class="ell" title="${esc(c.title)}">${esc(c.title)}</span>${c.why ? `<span class="why" style="margin:0">${esc(c.why)}</span>` : ""}${c.current > c.ranOn ? `<span class="drift">current is v${c.current}: run a new attempt</span>` : ""}</div>`).join("") +
  `</div></div>
  <div class="card" style="margin-top:20px"><div class="hd"><span class="eyebrow">History</span>Last ${f.history.length} runs of this feature</div><div class="bd stack">${f.history.map((h) => `<div class="runs-row"><span class="ell">${esc(`${h.ver} · ${h.env} · ${h.when}`)}</span>${bar(h.results)}<span class="num muted" style="text-align:right">${pct(h.results)}%</span></div>`).join("")}</div></div>`;
};

const empty = (d) => {
  const p = d.product;
  return head(`${orgLink(d)}${sep}<a href="${lnk("products.html")}">Products</a>${sep}<span>${productLabel(p)}</span>`, "Product report", esc(p.name), "product") +
  `<div class="card"><div class="empty"><div class="ill">${I.report}</div><h3>No results yet</h3><p style="margin:0">${esc(p.key)} has ${p.cases} cases but no cycle has recorded a result. Reports fill in once a cycle runs.</p><a class="btn primary" href="${lnk("cycles.html#new-cycle")}">${I.plus}New cycle</a></div></div>`;
};

const skel = () => `<div class="kpis" aria-busy="true">${[1, 2, 3, 4].map(() => `<div class="kpi"><span class="skel" style="width:40%"></span><span class="skel" style="height:24px;width:60%;margin-top:12px"></span></div>`).join("")}</div>
  <div class="card" style="margin-bottom:20px"><div class="hd"><span class="eyebrow">Trend</span>Results per day</div><div class="bd"><div class="chart">${[40, 62, 30, 18, 70, 66, 55, 60, 72, 35, 24, 80, 84, 68].map((h) => `<div class="col"><span class="skel" style="height:${h}%;border-radius:4px"></span></div>`).join("")}</div></div></div>
  <div class="card"><div class="hd"><span class="eyebrow">Products</span>By product</div><div class="bd stack">${[1, 2, 3, 4].map(() => `<span class="skel"></span>`).join("")}</div></div>`;

/* live: the level switch moves the hash; a period change gives feedback. Wired once, on the document. */
let wired = false;
function wire() {
  if (wired) return;
  wired = true;
  document.addEventListener("click", (e) => { const b = e.target.closest && e.target.closest("[data-level]"); if (b) location.hash = b.dataset.level; });
  document.addEventListener("dr:change", (e) => toast(`<div><b>Period: ${e.detail.value === "custom" ? "custom range" : esc(e.detail.value)}</b> <span class="muted">· reports refreshed</span></div>`));
}

export default { nav: "reports", default: "org", after: () => wire(), states: {
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
