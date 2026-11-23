/* Products: the catalog list, one product's detail and the new-product form. */
import { I, bar, crumbs, lnk, modal, dd, tg, toast, psearch, hl, esc, person } from "../ui.js";

const pcard = (p, q) => `<a class="card pc" href="${lnk("products.html#detail")}">
  <div class="pc-h"><span class="mark ${p.markCls}">${esc(p.key[0])}</span><div style="min-width:0"><h2>${hl(esc(p.key + " · " + p.name), q)}</h2><small class="ell">${hl(esc(p.desc), q)}</small></div></div>
  <div class="nums"><div><b>${p.features}</b><span>Features</span></div><div><b>${p.cases}</b><span>Cases</span></div><div><b>${p.versions}</b><span>Versions</span></div></div>
  ${Object.keys(p.results).length ? bar(p.results, "", `${esc(p.key)} · latest results`) : '<span class="faint" style="font-size:12px">No results yet</span>'}
  <div class="row"><span class="chip">${I.tag}${esc(p.latest)}</span></div></a>`;
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const catalog = (d) => head("Products", `Catalog · ${esc(d.ctx.org.name)}`, crumbs([["Catalog"], ["Products"]]), d.products.length ? newBtn : "");
const newBtn = `<a class="btn primary" href="#new">${I.plus}New product</a>`;
const intro = `<div class="sub" style="margin-bottom:16px">A product owns its <b>versions</b>, its <b>feature tree</b> (cases live under features) and its <b>test plans</b>. Cycles run a plan against a version.</div>`;
const S = (q, cnt) => psearch({ q, ph: "Search products by key, name or description", cnt, clear: "#search-cleared" });
const list = (d) => {
  const q = d.q;
  const all = d.created ? [d.created, ...d.products] : d.products;
  const hits = q ? all.filter((p) => (p.key + p.name + p.desc).toLowerCase().includes(q.toLowerCase())) : all;
  const body = hits.length ? `<div class="plist">${hits.map((p) => pcard(p, q)).join("")}</div>`
    : `<div class="card"><div class="empty"><div class="ill">${I.search}</div><h3>No products match “${esc(q)}”</h3><p class="muted">Search looks at the key, name and description. Try another word, or create the product.</p><div class="row" style="justify-content:center;gap:8px"><a class="btn" href="#search-cleared">Clear search</a><a class="btn primary" href="#new">${I.plus}New product</a></div></div></div>`;
  return catalog(d) + intro + S(q, `${hits.length} of ${d.products.length} products`) + body;
};

function detail(d) {
  const p = d.detail;
  const k = p.kpis;
  const label = esc(`${p.key} · ${p.name}`);
  const row = (h, ic, title, meta, right) => `<a class="lrow" href="${lnk(h)}"><span class="pi">${ic}</span><span class="m"><b>${title}</b><small>${meta}</small></span><span class="r">${right}</span></a>`;
  return head(label, "Product", crumbs([["Products", "products.html"], [label]]), `<a class="btn hide-n" href="${lnk("tree.html")}">${I.tree}Feature tree</a><a class="btn primary" href="${lnk("releases.html#new")}">${I.plus}New version</a>`) +
  `<div class="sub" style="margin:-10px 0 18px">${esc(p.desc)}. Owner: ${esc(person(p.owner)[0])}.</div>
  <div class="kpis"><div class="kpi"><div class="l">Versions</div><div class="v">${k.versions}</div><div class="d">${k.inProgress} in progress · ${k.planned} planned</div></div><div class="kpi"><div class="l">Features</div><div class="v">${k.features}</div><div class="d">${k.topLevel} top level</div></div><div class="kpi"><div class="l">Cases</div><div class="v">${k.cases}</div><div class="d">${k.automatedPct}% automated</div></div><div class="kpi"><div class="l">Test plans</div><div class="v">${k.plans}</div><div class="d">${k.plansActive} active</div></div></div>
  <div class="card gap"><div class="hd"><h2>Versions</h2><span class="faint" style="font-weight:400;font-size:12.5px">Each version lists the features it changes</span><a class="r btn ghost sm" href="${lnk("releases.html")}">All versions</a></div>
    ${p.versions.map((v) => row("releases.html#detail", I.tag, esc(p.key + " " + v.ver), `${esc(v.when)} · ${v.features} features · ${v.cycles} cycles`, `<span class="pill ${v.status}">${v.status.replace("_", " ")}</span><span class="bar-w">${Object.keys(v.results).length ? bar(v.results, "", esc(p.key + " " + v.ver)) : '<span class="faint" style="font-size:12px">No results yet</span>'}</span>`)).join("")}
  </div>
  <div class="g2">
    <div class="card"><div class="hd"><h2>Features</h2><a class="r btn ghost sm" href="${lnk("tree.html")}">Open tree</a></div>
      ${p.features.map((f) => row("tree.html", I.folder, esc(f.path), `${f.cases} cases · changed in ${esc(f.changedIn)}`, "")).join("")}
    </div>
    <div class="card"><div class="hd"><h2>Test plans</h2><a class="r btn ghost sm" href="${lnk("plans.html")}">All plans</a></div>
      ${p.plans.map((pl) => row(pl.href, I.flag, esc(pl.name), esc(pl.meta), `<span class="chip">${I.cycle}${pl.cycles} cycles</span>`)).join("")}
    </div>
  </div>`;
}

const form = (d) => {
  const f = d.draft;
  const copy = [{ v: "none", label: "Start empty", icon: I.plus }, "-", { group: "Products" },
    ...d.copyFrom.map((p) => ({ v: p.key, label: esc(`${p.key} · ${p.name}`), hint: `${p.features} features`, icon: `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>` }))];
  return modal("New product", `
  <div class="field"><label for="pk">Key</label><input id="pk" class="in mono" value="${esc(f.key)}" maxlength="10"><span class="faint" style="font-size:12px">Prefix for case numbers, e.g. ${esc(f.key)}-101. Can't change later.</span></div>
  <div class="field"><label for="pn">Name</label><input id="pn" class="in" value="${esc(f.name)}"></div>
  <div class="field"><label for="pd">Description</label><textarea id="pd" class="in" rows="3">${esc(f.desc)}</textarea></div>
  <div class="field"><label>Copy feature tree from</label>${dd({ value: "none", options: copy, w: "100%", label: "Copy feature tree from" })}</div>
  ${tg(true, "Create version 1.0.0 now", "Adds a planned version so plans and cycles have a target")}`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary">Create product</button>`);
};

const empty = (d) => catalog(d) + `<div class="card"><div class="empty"><div class="ill">${I.build}</div><h3>No products yet</h3><p class="muted">A product holds versions, a feature tree with its cases, and test plans. Start with one.</p><a class="btn primary" href="#new-first">${I.plus}New product</a></div></div>`;

export default { nav: "products", default: "list", states: {
  "list": { render: list },
  "search": { render: list },
  "search-empty": { render: list },
  "search-cleared": { render: list, after: (m, d) => toast(`Search cleared. <span class="muted">Showing all ${d.products.length} products.</span>`) },
  "detail": { render: detail },
  "new": { render: (d) => list(d) + form(d) },
  "created": { render: list, after: (m, d) => toast(`<b>${esc(d.created.key)} created.</b> <span class="muted">Add features, then cases. Audit: products.create by ${esc(person(d.ctx.user.handle)[0])}.</span>`, false, true) },
  "empty": { render: empty },
  "new-first": { render: (d) => catalog(d) + form(d) }
}};
