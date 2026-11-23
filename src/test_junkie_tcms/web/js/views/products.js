/* Products: the catalog list, one product's detail and the new-product form. The data and the writes are
   data/products.js; the list's search is the server's (the view never filters). */
import { I, bar, crumbs, modal, dd, tg, psearch, hl, esc, person } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions } from "../data/products.js";

const pcard = (p, q) => `<a class="card pc" href="${href("products", { id: p.key, product: p.key })}">
  <div class="pc-h"><span class="mark ${p.markCls}">${esc(p.key[0])}</span><div style="min-width:0"><h2>${hl(esc(p.key + " · " + p.name), q)}</h2><small class="ell">${hl(esc(p.desc), q)}</small></div></div>
  <div class="nums"><div><b>${p.features}</b><span>Features</span></div><div><b>${p.cases}</b><span>Cases</span></div><div><b>${p.versions}</b><span>Versions</span></div></div>
  ${Object.keys(p.results).length ? bar(p.results, "", `${esc(p.key)} · latest results`) : '<span class="faint" style="font-size:12px">No results yet</span>'}
  <div class="row"><span class="chip">${I.tag}${esc(p.latest)}</span></div></a>`;
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const catalog = (d) => head("Products", `Catalog · ${esc(d.ctx.org.name)}`, crumbs([["Catalog"], ["Products"]]), d.products.length ? newBtn : "");
const newBtn = `<a class="btn primary" href="#new">${I.plus}New product</a>`;
const intro = `<div class="sub" style="margin-bottom:16px">A product owns its <b>versions</b>, its <b>feature tree</b> (cases live under features) and its <b>test plans</b>. Cycles run a plan against a version.</div>`;
const cleared = () => href("products", {}, "search-cleared");
const S = (q, cnt) => psearch({ q, ph: "Search products by key, name or description", cnt, clear: cleared() });
/* d.products is what the server matched for d.q (products_list?q=); d.total counts every product */
const list = (d) => {
  const q = d.q;
  const hits = d.created ? [d.created, ...d.products] : d.products;
  const body = hits.length ? `<div class="plist">${hits.map((p) => pcard(p, q)).join("")}</div>`
    : `<div class="card"><div class="empty"><div class="ill">${I.search}</div><h3>No products match “${esc(q)}”</h3><p class="muted">Search looks at the key, name and description. Try another word, or create the product.</p><div class="row" style="justify-content:center;gap:8px"><a class="btn" href="${cleared()}">Clear search</a><a class="btn primary" href="#new">${I.plus}New product</a></div></div></div>`;
  return catalog(d) + intro + S(q, `${hits.length} of ${d.total} products`) + body;
};

function detail(d) {
  const p = d.detail;
  const k = p.kpis;
  const label = esc(`${p.key} · ${p.name}`);
  const row = (h, ic, title, meta, right) => `<a class="lrow" href="${h}"><span class="pi">${ic}</span><span class="m"><b>${title}</b><small>${meta}</small></span><span class="r">${right}</span></a>`;
  const at = { product: p.key };
  const about = [p.desc ? `${esc(p.desc)}.` : "", p.owner ? `Owner: ${esc(person(p.owner)[0])}.` : ""].filter(Boolean).join(" ");
  return head(label, "Product", crumbs([["Products", href("products")], [label]]), `<a class="btn hide-n" href="${href("tree", at)}">${I.tree}Feature tree</a><a class="btn primary" href="${href("releases", at, "new")}">${I.plus}New version</a>`) +
  `${about ? `<div class="sub" style="margin:-10px 0 18px">${about}</div>` : ""}
  <div class="kpis"><div class="kpi"><div class="l">Versions</div><div class="v">${k.versions}</div><div class="d">${k.inProgress} in progress · ${k.planned} planned</div></div><div class="kpi"><div class="l">Features</div><div class="v">${k.features}</div><div class="d">${k.topLevel} top level</div></div><div class="kpi"><div class="l">Cases</div><div class="v">${k.cases}</div><div class="d">${k.automatedPct}% automated</div></div><div class="kpi"><div class="l">Test plans</div><div class="v">${k.plans}</div><div class="d">${k.plansActive} active</div></div></div>
  <div class="card gap"><div class="hd"><h2>Versions</h2><span class="faint" style="font-weight:400;font-size:12.5px">Each version lists the features it changes</span><a class="r btn ghost sm" href="${href("releases", at)}">All versions</a></div>
    ${p.versions.map((v) => row(href("releases", { ...at, id: v.id }), I.tag, esc(p.key + " " + v.ver), `${esc(v.when)} · ${v.features} features · ${v.cycles} cycles`, `<span class="pill ${v.status}">${v.status.replace("_", " ")}</span><span class="bar-w">${Object.keys(v.results).length ? bar(v.results, "", esc(p.key + " " + v.ver)) : '<span class="faint" style="font-size:12px">No results yet</span>'}</span>`)).join("")}
  </div>
  <div class="g2">
    <div class="card"><div class="hd"><h2>Features</h2><a class="r btn ghost sm" href="${href("tree", at)}">Open tree</a></div>
      ${p.features.map((f) => row(href("tree", at), I.folder, esc(f.path), `${f.cases} cases${f.changedIn ? ` · changed in ${esc(f.changedIn)}` : ""}`, "")).join("")}
    </div>
    <div class="card"><div class="hd"><h2>Test plans</h2><a class="r btn ghost sm" href="${href("plans", at)}">All plans</a></div>
      ${p.plans.map((pl) => row(href("plans", { ...at, id: pl.id }), I.flag, esc(pl.name), esc(pl.meta), `<span class="chip">${I.cycle}${pl.cycles} cycles</span>`)).join("")}
    </div>
  </div>`;
}

const form = (d) => {
  const f = d.draft;
  const copy = [{ v: "none", label: "Start empty", icon: I.plus }, "-", { group: "Products" },
    ...d.copyFrom.map((p) => ({ v: p.key, label: esc(`${p.key} · ${p.name}`), hint: `${p.features} features`, icon: `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>` }))];
  return modal("New product", `
  <div class="field"><label for="pk">Key</label><input id="pk" class="in mono" value="${esc(f.key)}" maxlength="10"><span class="faint" style="font-size:12px">Prefix for case numbers, e.g. ${esc(f.key || "KEY")}-101. Can't change later.</span></div>
  <div class="field"><label for="pn">Name</label><input id="pn" class="in" value="${esc(f.name)}"></div>
  <div class="field"><label for="pd">Description</label><textarea id="pd" class="in" rows="3">${esc(f.desc)}</textarea></div>
  <div class="field"><label>Copy feature tree from</label>${dd({ value: "none", options: copy, w: "100%", label: "Copy feature tree from", name: "copy" })}</div>
  ${tg(true, "Create version 1.0.0 now", "Adds a planned version so plans and cycles have a target", { name: "v1" })}`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="create">Create product</button>`);
};

const empty = (d) => catalog(d) + `<div class="card"><div class="empty"><div class="ill">${I.build}</div><h3>No products yet</h3><p class="muted">A product holds versions, a feature tree with its cases, and test plans. Start with one.</p><a class="btn primary" href="#new-first">${I.plus}New product</a></div></div>`;

/* the real controls: the search box asks the server (Enter), and the form's Create button creates */
function after(main, state, d) {
  const box = main.querySelector(".psearch input");
  if (box) box.addEventListener("keydown", (e) => {
    if (e.key === "Enter") location.href = href("products", { q: box.value.trim() || null });
  });
  const create = main.querySelector("[data-act=create]");
  if (create) create.addEventListener("click", async () => {
    const val = (id) => main.querySelector("#" + id).value.trim();
    const copy = main.querySelector('[data-name="copy"] .dd-o.sel');
    create.disabled = true;
    try {
      const p = await actions.create({ key: val("pk"), name: val("pn"), desc: val("pd"), copyFrom: copy ? copy.dataset.v : "none", firstVersion: main.querySelector('input[name="v1"]').checked }, d.ctx);
      location.assign(href("products", { created: p.key, product: p.key }));
    } catch (e) {
      showError(main.querySelector(".modal .mb"), e, "Couldn't create the product.");
      create.disabled = false;
    }
  });
}

export default { nav: "products", default: "list", after, states: {
  "list": { render: list },
  "search": { render: list },
  "search-empty": { render: list },
  "search-cleared": { render: list, toast: (d) => `Search cleared. <span class="muted">Showing all ${d.products.length} products.</span>` },
  "detail": { render: detail },
  "new": { render: (d) => list(d) + form(d) },
  "created": { render: list, toastKeep: true, toast: (d) => `<b>${esc(d.created.key)} created.</b> <span class="muted">Add features, then cases. Recorded in the audit log.</span>` },
  "empty": { render: empty },
  "new-first": { render: (d) => catalog(d) + form(d) }
}};
