/* Test plans: the product's plan list, one plan's detail, the new-plan and edit-entries forms and making a cycle. */
import { I, bar, crumbs, lnk, modal, dd, tg, ver, psearch, hl, esc } from "../ui.js";

const pillOf = (s) => `<span class="pill ${s === "archived" ? "closed" : s}">${s}</span>`;
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const prodLabel = (d) => `${esc(d.ctx.product.key)} · ${esc(d.ctx.product.name)}`;
const mark = (p) => `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>`;
const listHead = (d) => head("Test plans", `Planning · ${prodLabel(d)}`, crumbs([[prodLabel(d), "products.html#detail"], ["Test plans"]]), `<a class="btn primary" href="#new">${I.plus}New plan</a>`);
const STATUS_OPTS = [{ v: "draft", label: "draft", dot: "var(--faint)" }, { v: "active", label: "active", dot: "var(--pass)" }, { v: "archived", label: "archived", dot: "var(--muted)" }];
const filters = (d) => `<div class="row wrap" style="gap:10px;margin-bottom:16px">${dd({ value: d.versionFilter, options: [{ v: "all", label: "All versions" }, "-", { group: `${d.ctx.product.key} versions` }, ...d.ctx.versions.map((v) => ({ v: v.ver, label: v.ver, hint: v.status, icon: I.tag }))], pre: "Version", cls: "sm", w: "190px", label: "Version" })}${dd({ multi: true, value: d.statusFilter, options: STATUS_OPTS, pre: "Status", cls: "sm", w: "200px", label: "Status" })}</div>`;
const S = (q, cnt) => psearch({ q, ph: "Search plans by name, feature or case", cnt, clear: "#search-cleared" });
const list = (d) => {
  const q = d.q, PL = d.plans, key = esc(d.ctx.product.key);
  const hits = q ? PL.filter((p) => (p.name + " " + p.scope).toLowerCase().includes(q.toLowerCase())) : PL;
  const rowsH = hits.map((p) => `<a class="pl" href="${lnk("plans.html#detail")}"><div class="n"><b class="ell">${hl(esc(p.name), q)}</b><small>${esc(p.scope)} · ${esc(p.cases)}</small></div><div>${pillOf(p.status)}</div><span class="s row">${I.tag}${esc(p.version)}</span>${Object.keys(p.results).length ? bar(p.results, "", esc(p.name) + " · last cycle") : '<span class="faint" style="font-size:12px">no cycle yet</span>'}</a>`).join("");
  const body = hits.length ? rowsH : `<div class="empty"><div class="ill">${I.search}</div><h3>No plans match “${esc(q)}”</h3><p class="muted" style="margin:0 auto 14px;max-width:420px">Search looks at plan names and the features and cases in them. Try a feature name, such as “Card payments”.</p><a class="btn" href="#search-cleared">Clear search</a> <a class="btn primary" href="#new">${I.plus}New plan</a></div>`;
  return listHead(d) + `<div class="sub">A plan says <b>what</b> to test for a version: whole features, single cases, or a query. Each cycle made from it pins the cases it resolves to.</div>` +
    S(q, hits.length + (hits.length === 1 ? " plan" : " plans")) + filters(d) +
    `<div class="card"><div class="hd"><h2>Plans in ${key}</h2><span class="r faint" style="font-size:12px">${hits.length} of ${PL.length}</span></div>${body}</div>`;
};

const KIND_ICON = { feature: I.folder, query: I.filter, case: I.doc };
const entries = (d, edit) => d.detail.entries.map((e) => `<div class="src"><span class="ic">${KIND_ICON[e.kind]}</span><div style="min-width:0"><div class="t1">${esc(e.label)}</div><div class="t2">${esc(e.meta)}</div></div><span class="r"><span class="kind">${e.kind}</span>${edit ? `<button class="icon-btn" aria-label="Remove">${I.x}</button>` : ""}</span></div>`).join("");
/* plan → resolve → pin → cycle; cur is the step in progress, past the last step every step is done */
const flow = (d, cur) => {
  const p = d.detail, r = p.resolve, c = p.cycles[0];
  const S4 = [["Plan", `${esc(p.name)}, ${p.entries.length} entries, scoped to ${esc(p.version)}`],
    ["Resolve", `${r.features} features → ${r.featureCases} cases; query adds ${r.queryNew} new; ${r.cases} case${r.cases === 1 ? "" : "s"}`],
    ["Pin", `${r.pinned} cases pinned at their current version (e.g. ${esc(r.example.key)} v${r.example.ver})`],
    ["Cycle", `${esc(c.name)}, ${esc(c.status)}`]];
  return `<div class="flow"${cur >= S4.length ? " data-done" : ""}>${S4.map((s, i) => `<div class="fs ${i < cur ? "done" : i === cur ? "cur" : ""}"><span class="no">${i < cur ? "✓" : i + 1}</span><h4>${s[0]}</h4><p>${s[1]}</p></div>`).join("")}</div>`;
};

function detail(d, banner = "", step = 0) {
  const p = d.detail, name = esc(p.name), v = esc(p.version);
  const L = (h, inner, cls = "") => `<a class="fx ${cls}" href="${lnk(h)}">${inner}</a>`;
  return head(name, `Test plan · ${esc(d.ctx.product.key)} ${v}`, crumbs([[prodLabel(d), "products.html#detail"], [v, "releases.html#detail"], ["Test plans", "plans.html"], [name]]),
    `<a class="btn" href="#edit">${I.edit}Edit entries</a><a class="btn hide-n" href="#create-cycle">${I.cycle}Create cycle only</a><a class="btn primary" href="${lnk("start.html#mode")}">${I.play}Run this plan</a>`) + banner +
  `<div class="card" style="margin-bottom:20px"><div class="hd"><h2>How this plan becomes a cycle</h2></div><div class="bd">${flow(d, step)}</div></div>
  <div class="g2">
    <div class="card"><div class="hd"><h2>What it tests</h2><span class="r">${pillOf(p.status)}<span class="faint" style="font-size:12px;margin-left:8px">${p.entries.length} entries</span></span></div><div class="bd">${entries(d, false)}</div></div>
    <div class="stack">
      <div class="card"><div class="hd"><h2>Scope</h2></div><div class="bd"><div class="fx-r">
        ${L("products.html#detail", `${I.build}<b>${prodLabel(d)}</b>`, "col")}${L("releases.html#detail", `${I.tag}<b>${v}</b><span class="r"><span class="pill ${p.versionStatus}">${p.versionStatus}</span></span>`, "col")}
      </div></div></div>
      <div class="card"><div class="hd"><h2>Cycles made from this plan</h2></div><div class="bd"><div class="fx-r">
        ${p.cycles.map((c) => L(c.href, `${I.cycle}<b>${esc(c.name)}</b><span class="r"><span class="pill ${c.status}">${c.status}</span><span class="faint hide-n">${c.pinned} pinned</span></span>`, "col")).join("\n        ")}
      </div><div style="margin-top:14px">${bar(p.latest.results, "", `Latest cycle · ${esc(p.latest.env)}`)}</div></div></div>
    </div>
  </div>`;
}

const newPlan = (d) => {
  const f = d.draft;
  const vers = f.versions.map((v) => ({ v: v.ver, label: v.ver, hint: v.status + (v.features ? ` · ${v.features} features` : ""), icon: I.tag }));
  return modal("New test plan", `
  <div class="field"><label for="pn">Name</label><input id="pn" class="in" value="${esc(f.name)}"></div>
  <div class="grid2"><div class="field"><label>Product</label>${dd({ value: f.product, options: d.ctx.products.map((p) => ({ v: p.key, label: `${p.key} · ${p.name}`, icon: mark(p) })), w: "100%", label: "Product" })}</div>
  <div class="field"><label>Version</label>${dd({ value: f.version, options: [{ v: "none", label: "Any version", hint: "a reusable plan, e.g. smoke" }, "-", { group: `${f.product} versions` }, ...vers], w: "100%", label: "Version", open: true })}</div></div>
  <div class="field"><label>Add tests by</label><div class="seg" role="group" aria-label="Add tests by"><button class="on" aria-pressed="true">${I.folder} Feature</button><button aria-pressed="false">${I.doc} Case</button><button aria-pressed="false">${I.filter} Query</button></div></div>
  ${tg(f.allFeatures, `Start with every feature in ${esc(f.version)}`, `Adds the ${f.featureCount} features from the version’s release_feature list`)}
  <div style="margin-top:14px">${entries(d, true)}</div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary">Create plan</button>`, "wide");
};

const createCycle = (d) => {
  const p = d.detail, c = d.newCycle;
  const envs = [...c.environments.map((e) => ({ v: e, label: e, icon: I.server })), "-", { v: "new", label: "New environment…", icon: I.plus }];
  return modal(`Create a cycle from ${esc(p.name)}`, `
  <div style="margin-bottom:18px">${flow(d, 2)}</div>
  <div class="grid2"><div class="field"><label>Environment</label>${dd({ value: c.env, options: envs, w: "100%", label: "Environment" })}</div>
  <div class="field"><label for="cn">Cycle name</label><input id="cn" class="in" value="${esc(c.name)}"></div></div>
  <div class="card" style="box-shadow:none"><div class="bd"><span class="kind" style="display:block;margin-bottom:10px">Resolved now</span><div class="res">
    ${c.resolved.map((r) => `<span>${esc(r.label)}</span><b>${r.count}${r.unit ? " " + esc(r.unit) : ""}</b>`).join("")}<span class="tot">Cases pinned at their current version</span><b class="tot">${p.resolve.pinned}</b>
  </div></div></div>
  <div style="margin-top:14px">${tg(c.skipDeprecated, "Skip deprecated cases", `${c.deprecated} deprecated cases match; they're left out by default`)}</div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary">Create cycle with ${p.resolve.pinned} cases</button>`, "wide");
};

const edit = (d) => modal("Edit entries", `<p class="muted" style="margin-top:0">Changes apply to new cycles. Cycles already made keep their pinned cases.</p>${entries(d, true)}<div class="row" style="margin-top:12px;gap:8px"><button class="btn sm">${I.folder}Add feature</button><button class="btn sm">${I.doc}Add case</button><button class="btn sm">${I.filter}Add query</button></div>`, `<button class="btn" data-back>Cancel</button><button class="btn primary">Save entries</button>`, "wide");

const created = (d) => {
  const p = d.detail, r = p.resolve;
  return detail(d, `<div class="banner info" style="margin-bottom:16px">${I.check}<div style="flex:1"><b>Cycle created: ${esc(p.cycles[0].name)}.</b> ${r.pinned} cases pinned (${esc(r.example.key)} at ${ver(r.example.ver, 1)}). <a href="${lnk("cycles.html#detail")}">Open cycle</a> · <a href="${lnk("run.html")}">Start running</a></div></div>`, 4);
};

const empty = (d) => listHead(d) + `<div class="card"><div class="empty"><div class="ill">${I.flag}</div><h3>No test plans for ${esc(d.ctx.product.key)}</h3><p class="muted" style="margin:0 auto 14px;max-width:460px">A plan picks features, cases or a query for a version. Create cycles from it as often as you need; each one pins the cases at their versions then.</p><a class="btn primary" href="#new">${I.plus}New plan</a></div></div>`;

export default { nav: "plans", default: "list", states: {
  "list": { render: list },
  "search": { render: list },
  "search-empty": { render: list },
  "search-cleared": { render: list, toast: (d) => `<div><b>Search cleared.</b> <span class="muted">Showing all ${d.plans.length} plans.</span></div>` },
  "detail": { render: (d) => detail(d) },
  "new": { render: (d) => list(d) + newPlan(d) },
  "edit": { render: (d) => detail(d) + edit(d) },
  "create-cycle": { render: (d) => detail(d) + createCycle(d) },
  "cycle-created": { render: created },
  "empty": { render: empty }
}};
