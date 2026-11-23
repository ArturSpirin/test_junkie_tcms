/* Features and cases: one product's feature tree with live drag and drop, the selected feature and its cases.
   The data and the writes are data/tree.js; the search, the filters and the sort are the server's. */
import { I, st, ver, dd, esc, bar, psearch, hl, rte, actor, toMd, crumbs, modal } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions } from "../data/tree.js";

/* ---------- tree model: features (t "f", with kids) and cases (t "c") ---------- */
function find(list, id, parent = null) {
  for (let i = 0; i < list.length; i++) {
    const x = list[i];
    if (x.id === id) return { node: x, list, i, parent };
    if (x.kids) { const r = find(x.kids, id, x); if (r) return r; }
  }
  return null;
}
const depthOf = (list, id, d = 0) => {
  for (const x of list) {
    if (x.id === id) return d;
    const r = x.kids ? depthOf(x.kids, id, d + 1) : -1;
    if (r >= 0) return r;
  }
  return -1;
};
const count = (x) => (x.t === "c" ? 1 : (x.more || 0) + x.kids.reduce((a, k) => a + count(k), 0));
const within = (a, b) => a.id === b.id || (a.kids || []).some((k) => within(k, b));
const name = (x) => (x.t === "c" ? x.key : x.name);
const isOpen = (x) => x.t === "f" && x.kids.length > 0 && !!x.open;

/* ---------- keyboard (WAI-ARIA tree pattern): pure, so the tests run them under node on the real data ---------- */
/* the rows on screen, in order */
function visible(list, parent = null, out = []) {
  for (const x of list) {
    out.push({ id: x.id, t: x.t, parent, hasK: x.t === "f" && x.kids.length > 0, open: isOpen(x) });
    if (isOpen(x)) visible(x.kids, x.id, out);
  }
  return out;
}
/* what a key on the focused row does: { focus: id }, { toggle: id }, { open: href } or null */
function navKey(model, id, key) {
  const v = visible(model), i = v.findIndex((r) => r.id === id), r = v[i];
  if (!r) return v.length ? { focus: v[0].id } : null;
  switch (key) {
    case "ArrowDown": return { focus: v[Math.min(i + 1, v.length - 1)].id };
    case "ArrowUp": return { focus: v[Math.max(i - 1, 0)].id };
    case "Home": return { focus: v[0].id };
    case "End": return { focus: v[v.length - 1].id };
    case "ArrowRight": return r.hasK ? (r.open ? { focus: v[i + 1].id } : { toggle: id }) : null;
    case "ArrowLeft": return r.open ? { toggle: id } : r.parent ? { focus: r.parent } : null;
    case "Enter": return { open: r.t === "c" ? href("case", { id }) : href("tree", { feature: id }) };
  }
  return null;
}
/* every place a keyboard move can drop src, in screen order, one per gap between rows: the places drag reaches.
   "after" an open feature stays only when it is last in its list (no "before" below it covers that gap).
   start is the index of the first place below src. Places check() refuses stay in, so the bar says why. */
function slots(model, src) {
  const list = [];
  let start = 0;
  const walk = (xs) => xs.forEach((x, i) => {
    const me = x.id === src;
    if (!me && (i === 0 || isOpen(xs[i - 1]))) list.push({ id: x.id, z: "before" });
    if (!me && x.t === "f") list.push({ id: x.id, z: "in" });
    if (me) start = list.length;
    if (isOpen(x)) walk(x.kids);
    if (!me && (!isOpen(x) || i === xs.length - 1)) list.push({ id: x.id, z: "after" });
  });
  walk(model);
  return { list, start };
}
/* the place one step down (dir 1) or up (dir -1) from place cur, or from src when cur is null; null when there is none */
function stepSlot(sl, cur, dir) {
  const i = cur == null ? (dir > 0 ? sl.start : sl.start - 1) : cur + dir;
  return i >= 0 && i < sl.list.length ? i : cur;
}

/* ---------- option sets (fixed choices; the product, tag and destination lists come from data) ---------- */
const PRI_COL = { critical: "var(--fail)", high: "var(--blocked)", medium: "var(--retest)", low: "var(--faint)" };
const AUTO_IC = { manual: I.person, automated: I.bolt, to_automate: I.spark };
const OPTS = {
  life: [{ group: "Case status" },
    { v: "draft", label: "draft", hint: "Work in progress", dot: "var(--faint)" },
    { v: "ready", label: "ready", hint: "Can be added to cycles", dot: "var(--pass)" },
    { v: "deprecated", label: "deprecated", hint: "Kept for history, not added to new cycles", dot: "var(--untested)" },
    "-", { group: "Edited" },
    { v: "7d", label: "Changed in the last 7 days", icon: I.clock },
    { v: "me", label: "Edited by me", icon: I.person },
    { v: "agent", label: "Edited by an agent", icon: I.agent }],
  result: [{ group: "Test Junkie result" },
    { v: "success", label: "success", hint: "Ran and passed", dot: "var(--st-success)" },
    { v: "fail", label: "fail", hint: "An assertion failed", dot: "var(--st-fail)" },
    { v: "error", label: "error", hint: "Unexpected exception", dot: "var(--st-error)" },
    { v: "ignore", label: "ignore", hint: "Ignored by a rule", dot: "var(--st-ignore)" },
    { v: "skip", label: "skip", hint: "Skipped, with a reason", dot: "var(--st-skip)" },
    { v: "cancel", label: "cancel", hint: "Run was cancelled", dot: "var(--st-cancel)" },
    "-", { v: "untested", label: "untested", hint: "No result yet in an open cycle", dot: "var(--st-untested)" }],
  auto: [{ group: "Automation" },
    { v: "manual", label: "manual", hint: "Run by a person in a cycle", icon: I.person },
    { v: "automated", label: "automated", hint: "Results come from the Test Junkie reporter", icon: I.bolt },
    { v: "to_automate", label: "to_automate", hint: "Manual today, queued for automation", icon: I.spark },
    "-", { group: "Automation ref" },
    { v: "ref", label: "Has an automation ref", icon: I.link },
    { v: "noref", label: "No automation ref", icon: I.x }],
  pri: [{ group: "Priority" }, ...[["critical", "Blocks a release"], ["high", "Run in every cycle"], ["medium", "Run when the area changes"], ["low", "Run before major releases"]].map(([v, h], i) => ({ v, label: v, hint: h, dot: PRI_COL[v], kbd: String(i + 1) }))],
  sort: [{ group: "Sort cases by" },
    { v: "manual", label: "Manual order", short: "Manual order", hint: "Your drag order, shared with the team", icon: I.drag },
    { v: "key", label: "Key", icon: I.tag },
    { v: "title", label: "Title A to Z", icon: I.doc },
    { v: "updated", label: "Last updated", icon: I.clock },
    { v: "result", label: "Last result, fail first", icon: I.okcirc },
    { v: "priority", label: "Priority, critical first", icon: I.flag }]
};
/* dd() escapes option labels, hints and groups itself */
const prodOpts = (d) => [{ group: `${d.ctx.org.name} products` },
  ...d.products.map((p) => ({ v: p.key, label: p.name, short: p.short, hint: p.features ? `${p.cases} cases · ${p.features} features` : "No features yet", icon: `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>` })),
  "-", { group: "Archived" },
  ...d.archived.map((p) => ({ v: p.key, label: p.name, hint: `Archived ${p.archivedOn} · read only`, icon: I.lock, dis: true })),
  "-", { v: "new", label: "New product…", icon: I.plus }];
const tagOpts = (d) => [{ group: `Tags in ${d.product.key}` }, ...d.tags.map((t) => ({ v: t.tag, label: "#" + t.tag, short: t.tag, hint: t.cases + " cases", icon: I.tag }))];
const destOpts = (d) => [{ group: `${d.product.name} · ${d.product.key}` }, ...d.move.dests.map((x) => ({ v: x.v, label: x.label, hint: x.hint, icon: x.root ? I.tree : I.folder, dis: !!x.dis }))];

/* ---------- tree ---------- */
function rows(list, d, o) {
  return list.map((x) => {
    const hasK = x.t === "f" && x.kids.length;
    const open = hasK && x.open;
    const cls = ["n", x.t === "c" ? "case" : "", o.cls[x.id] || "", o.sel === x.id ? "on" : ""].join(" ").replace(/\s+/g, " ").trim();
    const body = x.t === "c"
      ? `${I.doc}<span class="key">${hl(esc(x.key), o.q)}</span><span class="ell" title="${esc(x.title)}">${hl(esc(x.title), o.q)}</span>${st(x.last, { label: false })}`
      : `${I.folder}<span class="ell">${hl(esc(x.name), o.q)}</span><span class="c">${count(x)}</span>`;
    const more = open && x.more && x.kids.some((k) => k.t === "c") ? `<li class="more" style="--d:${d + 1}">+${x.more} more cases · <a href="${href("cases", { feature: x.id })}">show all</a></li>` : "";
    const add = o.newUnder === x.id ? newRow(o, d + 1) : "";
    return `<li><div class="${cls}" style="--d:${d}" data-id="${esc(x.id)}" data-t="${x.t}"${o.ro ? "" : ' draggable="true"'} tabindex="${o.focus === x.id ? 0 : -1}" role="treeitem"${hasK ? ` aria-expanded="${open}"` : ""}>` +
      `${o.ro ? "" : `<span class="gh" title="Drag to move">${I.drag}</span>`}<span class="tw${hasK && !open ? " closed" : ""}"${hasK ? " data-tw" : ""}>${hasK ? I.chevd : ""}</span>${body}<span class="nd" title="Not allowed here">${I.ban}</span></div>` +
      `${o.ext[x.id] || ""}${open || add ? `<ul role="group">${open ? rows(x.kids, d + 1, o) : ""}${more}${add}</ul>` : ""}</li>`;
  }).join("");
}
/* the new feature's name row, under a feature or at the top level */
const newRow = (o, d) => `<li class="newrow"><div class="n" style="--d:${d}"><span class="gh"></span><span class="tw"></span>${I.folder}<input class="in" value="${esc(o.d.newName)}" aria-label="New feature name" autofocus></div></li>`;
/* the search is the server's: d.tree holds only its matches, d.hits counts the cases and d.feats the features it found */
const cleared = () => href("tree", {}, "search-cleared");
function treeCard(o) {
  const d = o.d;
  let body;
  if (o.emptyProduct) body = '<li class="faint" style="padding:10px 20px;font-size:13px">No features yet</li>';
  else if (o.q && !o.model.length) body = `<li class="tnone"><b>No features or cases match “${esc(o.q)}”</b><span>Search looks at feature names, case keys and case titles in ${esc(d.product.key)}.</span><a href="${cleared()}">Clear search</a></li>`;
  else body = rows(o.model, 0, o);
  if (o.newUnder === "root") body = (o.emptyProduct ? "" : body) + newRow(o, 0);
  const cnt = o.q ? (o.model.length ? `${d.hits} cases · ${d.feats} features` : "0 results") : "";
  return `<div class="card tcard"><div class="hd"><div class="tch"><span class="eyebrow">Product</span>${dd({ value: d.picked, options: prodOpts(d), cls: "sm block", search: "Find a product", label: "Product", name: "product" })}</div>${o.ro ? "" : `<button class="icon-btn" data-hash="new-feature" title="New feature" aria-label="New feature">${I.plus}</button>`}</div>
  <div class="dnd-slot">${o.emptyProduct ? "" : psearch({ q: o.q, ph: "Search features and cases", cnt, clear: cleared() })}<div class="dnd-bar${o.barBad ? " bad" : ""}" id="dndbar" role="status"${o.bar ? "" : " hidden"}>${o.bar || ""}</div></div>
  <ul class="tree" id="tree" role="tree" aria-label="Features and cases">${body}</ul>
  ${o.ro || o.emptyProduct ? "" : `<div class="tfoot">${I.drag}<span>Drag any feature or case. Drop on a feature to put it inside; drop between rows to reorder. Or Space to pick up, arrows, Enter.</span></div>`}</div>`;
}

/* ---------- case list ---------- */
/* d.cases is the server's page of the selected feature's cases (with its sub-features'), already filtered,
   searched and sorted; d.casesTotal counts every match */
function casesCard(o) {
  const fe = o.d.feature;
  const list = o.d.cases;
  const tags = (c) => esc(c.tags.map((t) => "#" + t).join(" "));
  const pri = (p) => `<span class="pri"><span class="dot" style="--c:${PRI_COL[p]}"></span>${p}</span>`;
  const rowsH = list.map((c, i) => `<tr class="${c.life === "deprecated" ? "dim" : ""}${i === 0 && !o.filter ? " sel" : ""}" data-id="${esc(c.id)}"${o.ro ? "" : ' draggable="true"'}>
    <td class="g">${o.ro ? "" : `<span class="gh" title="Drag onto a feature">${I.drag}</span>`}</td><td class="key">${esc(c.key)}</td>
    <td class="tt"><a href="${href("case", { id: c.id })}" class="ell" title="${esc(c.title)}">${hl(esc(c.title), o.q)}</a><div class="faint sub"><span class="auto">${AUTO_IC[c.auto]}${c.auto}</span>${pri(c.pri)}${c.tags.length ? `<span>${tags(c)}</span>` : ""}</div></td>
    <td>${ver(c.ver)}</td><td><span class="pill ${c.life}">${c.life}</span></td><td>${st(c.last)}</td></tr>`).join("");
  const mrows = list.map((c) => `<div class="it"><div class="row"><span class="key">${esc(c.key)}</span>${ver(c.ver)}<span class="pill ${c.life}">${c.life}</span>${st(c.last)}</div><a href="${href("case", { id: c.id })}">${esc(c.title)}</a><span class="auto">${AUTO_IC[c.auto]}${c.auto} · ${c.pri}</span></div>`).join("");
  return `<div class="card"><div class="hd"><div class="tch"><span class="eyebrow">${esc(fe.parent)} / ${esc(fe.name)}</span><span class="row">${esc(fe.name)} <span class="faint" style="font-weight:400">${o.d.casesTotal} of ${fe.stats.cases}</span></span></div>
    <span class="r">${o.ro ? "" : `<a class="btn sm hide-n" href="${href("cycles", { feature: fe.id }, "new-cycle")}">${I.cycle}New cycle</a><a class="btn sm primary" href="${href("case", { feature: fe.id }, "new-case")}">${I.plus}New case</a>`}</span></div>
    <div class="tbl-wrap mswap"><table class="t"><thead><tr><th></th><th>Key</th><th>Title</th><th>Version</th><th>Status</th><th>Last result</th></tr></thead><tbody>${rowsH}</tbody></table></div>
    <div class="mlist">${mrows}</div></div>`;
}

/* ---------- feature description: people edit it here, agents through MCP features_update (PATCH /features/{id}) ---------- */
function descBlock(o) {
  const fe = o.d.feature;
  const m = o.desc || (fe.agentEdit ? "agent" : "view");
  if (m === "edit") return `<div class="fdesc"><div class="sec-h"><h2>Description</h2></div>
    ${rte({ html: fe.desc, compact: true, focus: true, label: "Feature description", foot: `<span class="faint">Markdown shortcuts work</span>` })}
    <div class="row" style="justify-content:flex-end;margin-top:10px"><a class="btn sm" href="#default">Cancel</a><button class="btn sm primary" data-act="save-desc">Save description</button></div></div>`;
  const a = fe.agentEdit;
  /* the API names a feature's last editor only: no via, on-behalf-of, change history or revert for a feature */
  const meta = m === "agent" && a
    ? `<div class="desc-meta agent">${actor("agent", esc(a.agent))}<span>edited ${esc(a.when)}</span></div>`
    : fe.edited ? `<div class="desc-meta">${actor("person", fe.edited.by)}<span>edited ${esc(fe.edited.when)}</span></div>` : "";
  return `<div class="fdesc"><div class="sec-h"><h2>Description</h2>${o.ro ? "" : `<a class="btn sm ghost r" href="#desc-edit">${I.edit}Edit</a>`}</div>
    <div class="rich fd-body">${fe.desc}</div>${meta}</div>`;
}

/* ---------- feature panel: coverage + where the feature is used (release_feature, plan_entry, cycle) ---------- */
function featureCard(o) {
  const fe = o.d.feature;
  const s = fe.stats;
  const L = (h, inner) => `<a class="fx" href="${h}">${inner}</a>`;
  return `<div class="card fcard"><div class="hd"><div class="tch"><span class="eyebrow">Feature · ${esc(fe.parent)}</span><span class="row">${I.folder}${esc(fe.name)}</span></div>${fe.owner ? `<span class="r faint" style="font-size:12px">owner ${esc(fe.owner)}</span>` : ""}</div>
  <div class="bd">
    ${descBlock(o)}
    <div class="fk"><div><span class="l">Cases</span><b>${s.cases}</b><small>${s.ready} ready · ${s.draft} draft</small></div><div><span class="l">Automated</span><b>${s.automatedPct}%</b><small>${s.automated} of ${s.cases} · ${s.toAutomate} to_automate</small></div><div><span class="l">Ran in ${esc(s.ranIn)}</span><b>${s.ran} of ${s.cases}</b><small>pinned versions</small></div></div>
    <div class="fcov"><span class="l">Latest result per case</span>${bar(fe.latest, "", esc(`${fe.name} · ${s.ranIn}`))}</div>
    <div class="fx-g"><span class="l">In versions</span><div class="fx-r">${fe.versions.map((v) => L(href("releases", { id: v.id }), `${I.tag}<b>${esc(v.ver)}</b><span class="pill ${v.status}">${v.status}</span>`)).join("")}</div></div>
    <div class="fx-g"><span class="l">Used by test plans</span><div class="fx-r">${fe.plans.map((p) => L(href("plans", { id: p.id }), `${I.flag}<b>${esc(p.name)}</b><span class="faint">${esc(p.scope)}</span>`)).join("")}</div></div>
    <div class="fx-g"><span class="l">In cycles</span><div class="fx-r">${fe.cycles.map((c) => L(href("cycles", { id: c.id }), `${I.cycle}<b>${esc(c.name)}</b><span class="pill ${c.status}">${c.status}</span>${c.pinned ? `<span class="faint">${c.pinned} pinned</span>` : ""}`)).join("")}</div></div>
  </div></div>`;
}

/* ---------- filters (all dropdowns are dd) ---------- */
function filters(o) {
  const d = o.d, v = o.filter;
  return `<div class="filters">
    ${dd({ multi: true, value: v ? v.tag : [], options: tagOpts(d), search: "Find a tag", pre: "Tag", placeholder: "Any", cls: "sm", w: "170px", open: o.open === "tag", name: "tag", label: "Tag" })}
    ${dd({ multi: true, value: v ? v.status : [], options: OPTS.life, pre: "Status", placeholder: "Any", cls: "sm", w: "184px", name: "status", label: "Status" })}
    ${dd({ multi: true, value: v ? v.result : [], options: OPTS.result, pre: "Last result", placeholder: "Any", cls: "sm", w: "170px", name: "result", label: "Last result" })}
    ${dd({ multi: true, value: v ? v.automation : [], options: OPTS.auto, pre: "Automation", placeholder: "Any", cls: "sm", w: "214px", name: "automation", label: "Automation" })}
    ${dd({ multi: true, value: v ? v.priority : [], options: OPTS.pri, pre: "Priority", placeholder: "Any", cls: "sm hide-n", w: "150px", name: "priority", label: "Priority" })}
    ${v ? '<button class="btn ghost sm" data-act="clear-filters">Clear</button>' : ""}<span class="sp"></span>
    ${dd({ value: d.sort, options: OPTS.sort, pre: "Sort", cls: "sm ghost", w: "196px", name: "sort", label: "Sort" })}
  </div>`;
}

const head = (d, ro) => `${crumbs([[esc(`${d.product.key} · ${d.product.name}`), href("products", { id: d.product.key })], ["Features", href("tree")], ...(d.feature ? [[esc(d.feature.parent)], [esc(d.feature.name)]] : [])])}
  <div class="ph"><div class="ttl"><span class="eyebrow">Features and cases · ${esc(d.product.key)}</span><h1>Features</h1></div>${ro ? `<span class="chip">${esc(d.ctx.user.role)} · read only</span>` : ""}<div class="actions">${ro ? "" : `<button class="btn hide-n">${I.upload}Import</button><button class="btn" data-hash="new-feature">${I.plus}New feature</button>`}</div></div>`;
const ghost = (d, inner, gx, o = {}) => `<div class="dghost${o.bad ? " bad" : ""}${o.top ? " at-top" : ""}" style="--d:${d}" aria-hidden="true">${inner}${gx ? `<div class="gx">${gx}</div>` : ""}</div>`;
/* why a drop is not allowed, or "" */
function check(model, src, tgt, z) {
  const s = find(model, src).node, t = find(model, tgt);
  const dest = z === "in" ? t.node : t.parent;
  if (s.t === "f" && dest && within(s, dest)) return `Can't move '${esc(s.name)}' into '${esc(dest.name)}': a feature can't go inside itself or its own sub-feature.`;
  if (s.t === "c" && !dest) return `A case has to sit inside a feature. Drop ${esc(s.key)} on a feature.`;
  return "";
}
/* a drag frozen mid-way (the drag-* states): marks on the rows, the drag bar and the ghost under the row hovered */
function dragPreview(o, g) {
  const s = find(o.model, g.src).node, t = find(o.model, g.over), dep = depthOf(o.model, g.over);
  const why = check(o.model, g.src, g.over, g.zone);
  const chip = (x) => `<b>${esc(x.name)}</b><span class="chip mono">${count(x)}</span>`;
  o.cls[g.src] = "dragging";
  if (why) {
    o.cls[g.over] = "nodrop"; o.barBad = true;
    o.bar = `${I.ban}<span>${why}</span>`;
    o.ext[g.over] = ghost(dep, `${I.ban}${I.folder}${chip(s)}`, `<span>Not allowed: '${esc(t.node.name)}' is inside '${esc(s.name)}'. Drop on another feature, or press Esc.</span>`, { bad: true });
  } else if (g.zone === "in") {
    o.cls[g.over] = "drop";
    o.bar = `${I.drag}<span>Dragging <b>${esc(name(s))}</b>${s.t === "f" ? ` (${count(s)} cases)` : ""} · Esc cancels</span>`;
    o.ext[g.over] = ghost(dep, `${I.drag}${I.folder}${chip(s)}`, `${I.arrowdn}<span>Sub-feature of <b>${esc(t.node.name)}</b></span>`);
  } else {
    o.cls[g.over] = g.zone === "before" ? "ins-b" : "ins-a";
    o.bar = `${I.drag}<span>Dragging <b>${esc(name(s))}</b> · drop between rows to reorder</span>`;
    const sibs = t.list.filter((x) => x.t === s.t && x.id !== s.id);
    const pos = sibs.indexOf(t.node) + (g.zone === "before" ? 1 : 2);
    const up = t.list.indexOf(s) > t.i;
    o.ext[g.over] = ghost(dep, s.t === "c" ? `${I.drag}${I.doc}<span class="key">${esc(s.key)}</span><b class="ell">${esc(s.title)}</b>` : `${I.drag}${I.folder}${chip(s)}`,
      `${up ? I.arrowup : I.arrowdn}<span>Position ${pos} of ${sibs.length + 1} in ${esc(t.parent ? t.parent.name : o.d.product.name)}</span>`, { top: g.zone === "before" });
  }
}
/* everything one render of the page needs: data d plus the state's UI options */
function opts(d, ui = {}) {
  const o = { ...ui, d, sel: d.sel, q: d.q, filter: d.filter, ro: d.readOnly, newUnder: d.newUnder, emptyProduct: d.empty, model: d.tree, cls: {}, ext: {}, bar: "", barBad: false };
  if (d.move) { o.cls[d.move.src] = "ghost"; o.cls[d.move.dest] = "drop"; }
  if (d.moved) o.cls[d.moved] = "just";
  if (d.drag) dragPreview(o, d.drag);
  o.focus = rover(o.model, d.moved || o.sel);
  return o;
}
/* the tree's one tab stop (roving tabindex): the row asked for if it is on screen, else the first row */
function rover(model, id) {
  const v = visible(model);
  return v.some((r) => r.id === id) ? id : v.length ? v[0].id : null;
}
const right = (o) => {
  if (!o.emptyProduct) return featureCard(o) + casesCard(o);
  const p = o.d.products.find((x) => x.key === o.d.picked);
  return `<div class="card"><div class="empty"><div class="ill">${I.tree}</div><h3>No features in ${esc(p ? p.name : o.d.picked)}</h3><div>Add a feature, then cases under it. Or import from CSV or Markdown.</div>${o.ro ? "" : `<button class="btn primary" data-hash="new-feature">${I.plus}New feature</button> <button class="btn">${I.upload}Import</button>`}</div></div>`;
};
function layout(d, ui) {
  const o = opts(d, ui);
  return head(d, o.ro) + (o.banner || "") + filters(o) + `<div class="split"><div id="tcol">${treeCard(o)}</div><div id="ccol">${right(o)}</div></div>`;
}

/* a feature's name, or the product's for the top level ("root") */
const nameOf = (d, id) => (id === "root" ? d.product.name : find(d.tree, id).node.name);
const newBanner = (d) => `<div class="banner info">${I.info}<div>New feature ${d.newUnder === "root" ? "at the top level of" : "under"} <b>${esc(nameOf(d, d.newUnder))}</b>. Enter saves, Esc cancels.</div></div>`;
function moveModal(d) {
  const s = find(d.tree, d.move.src).node;
  return modal(`Move '${esc(s.name)}'`,
    `<p style="margin-top:0">Moving <b>${esc(s.name)}</b> (${count(s)} cases) under <b>${esc(nameOf(d, d.move.dest))}</b>. Its cases and their versions move with it.</p>
    <div class="field"><label>Destination feature</label>${dd({ value: d.move.dest, options: destOpts(d), cls: "block", search: "Find a feature", open: true, label: "Destination feature", name: "dest" })}</div>
    <div class="field mb0"><label>Position</label><div class="seg" data-name="at"><button class="on" data-v="end">Inside, at the end</button><button data-v="top">Inside, at the top</button></div></div>`,
    `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="move">Move here</button>`);
}
/* The move toast's text, for the live drop and the dropped state: before/after on a reorder within the same parent, "into" otherwise. */
function movedMsg(s, same, dest, z, t, product) {
  const dl = esc(dest ? dest.name : product), sn = esc(name(s));
  const where = !same ? `into '${dl}'` : z === "in" ? `to the end of '${dl}'` : `${z} '${esc(name(t))}'`;
  return `<div><b>Moved '${sn}' ${where}.</b> <span class="muted">${s.t === "f" ? `${count(s)} cases moved with it` : "Its versions and results stay with it"}</span></div>`;
}
function droppedToast(d) {
  const m = find(d.tree, d.moved);
  return `<div class="toast" role="status">${movedMsg(m.node, false, m.parent, "in", null, d.product.name)}<button class="btn sm" data-act="undo" aria-keyshortcuts="Control+Z" title="Undo (Ctrl+Z)">Undo</button></div>`;
}
const loading = (d) => head(d) + `<div class="split"><div class="card"><div class="bd stack">${"<span class='skel'></span>".repeat(8)}</div></div><div class="card"><div class="bd stack">${"<span class='skel' style='height:18px'></span>".repeat(6)}</div></div></div>`;
const error = (d) => head(d) + `<div class="banner err">${I.warn}<div style="min-width:0;flex:1"><b>Couldn't load the tree.</b> The server said:
<pre class="raw">${esc(d.error)}</pre></div><div class="r"><button class="btn sm" data-act="retry">Retry</button></div></div>`;

/* ---------- live HTML5 drag and drop, keyboard and twisties (browser only, wired once from after) ---------- */
/* CUR: the render options of the state on the page; D: its data; MODEL: the tree as drawn (twisties change it);
   KEY: a keyboard move under way, { src, sl: slots(), i: the place index or null } */
let CUR = null, D = null, MODEL = null, SRC = null, KEY = null, wired = false;
const NAV_KEYS = ["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Home", "End", "Enter"];
function paint() {
  const t = document.getElementById("tcol"), c = document.getElementById("ccol");
  CUR.focus = rover(CUR.model, CUR.focus);
  if (t) t.innerHTML = treeCard(CUR);
  if (c && !CUR.emptyProduct) c.innerHTML = featureCard(CUR) + casesCard(CUR);
}
function setBar(html, bad) {
  const b = document.getElementById("dndbar");
  if (!b) return;
  b.hidden = !html; b.classList.toggle("bad", !!bad);
  b.innerHTML = html ? `${bad ? I.ban : I.drag}<span>${html}</span>` : "";
}
function zone(n, e) {
  const r = n.getBoundingClientRect(), y = (e.clientY - r.top) / r.height;
  if (n.dataset.t === "f") return y < 0.28 ? "before" : y > 0.72 ? "after" : "in";
  return y < 0.5 ? "before" : "after";
}
function clearMarks() { document.querySelectorAll("#tree .n.drop, #tree .n.ins-b, #tree .n.ins-a, #tree .n.nodrop").forEach((x) => x.classList.remove("drop", "ins-b", "ins-a", "nodrop")); }
/* the row mark and bar text for src over row n at zone z, shared by drag and the keyboard move; false when not allowed */
function markDrop(n, src, z) {
  const why = check(MODEL, src, n.dataset.id, z);
  if (why) { n.classList.add("nodrop"); setBar(why, true); return false; }
  n.classList.add(z === "in" ? "drop" : z === "before" ? "ins-b" : "ins-a");
  const t = find(MODEL, n.dataset.id);
  setBar(z === "in" ? `Drop into <b>${esc(t.node.name)}</b>${find(MODEL, src).node.t === "f" ? ": becomes a sub-feature" : ""}` : `Drop ${z} <b>${esc(name(t.node))}</b> in ${esc(t.parent ? t.parent.name : CUR.d.product.name)}`);
  return true;
}
const rowEl = (id) => document.querySelector(`#tree .n[data-id="${CSS.escape(id)}"]`);
/* make row n the tree's one tab stop */
function rove(n) {
  document.querySelectorAll('#tree .n[tabindex="0"]').forEach((x) => x !== n && x.setAttribute("tabindex", "-1"));
  n.setAttribute("tabindex", "0"); CUR.focus = n.dataset.id;
}
function focusRow(id) {
  const n = rowEl(id) || document.querySelector('#tree .n[tabindex="0"]');
  if (n) { rove(n); n.focus(); }
}
/* ends a keyboard move: marks, dim and bar cleared; returns its src */
function endKeyMove() {
  const s = KEY.src;
  KEY = null; clearMarks(); setBar(null);
  document.querySelectorAll("#tree .n.dragging").forEach((x) => x.classList.remove("dragging"));
  return s;
}
/* Where dropping src on tgt (zone z) puts it: the new parent (a feature id, or null for the top level) and its
   index among the siblings of its kind (null appends a case), and where it was (from: "" for the top level).
   Shared by drag and the keyboard move; model defaults to the tree on the page. */
function place(src, tgt, z, model = MODEL) {
  const m = JSON.parse(JSON.stringify(model));
  const a = find(m, src); a.list.splice(a.i, 1);
  const s = a.node, t = find(m, tgt);
  const from = s.t === "c" ? s.fid : (a.parent ? a.parent.id : "");
  if (z === "in") return { s, from, parent: t.node.id, position: s.t === "f" ? t.node.kids.filter((x) => x.t === "f").length : null };
  const at = z === "before" ? t.i : t.i + 1;
  return { s, from, parent: t.parent ? t.parent.id : null, position: t.list.slice(0, at).filter((x) => x.t === s.t).length };
}
/* the server moves it; the page then reloads on the moved row, with what Undo needs in the URL */
async function move(src, tgt, z) {
  const p = place(src, tgt, z), ctx = D.ctx;
  try {
    if (p.s.t === "f") await actions.moveFeature(src, p.parent, p.position, ctx);
    else await actions.moveCase(src, p.parent, p.position, ctx);
    location.assign(href("tree", { feature: p.s.t === "f" ? src : p.parent, moved: src, from: p.from, pos: p.s.pos }, "dropped"));
  } catch (e) {
    showError(document.querySelector("#tcol .tcard"), e, `Couldn't move '${name(p.s)}'.`);
  }
}
/* a control's async write: the button stays disabled while it runs, a failure shows raw in el */
async function act(btn, el, label, run) {
  btn.disabled = true;
  try { await run(); } catch (e) { showError(el, e, label); btn.disabled = false; }
}
/* the filters and sort in the URL, from the dropdowns on the page */
function filterHref(main, clear) {
  const picked = (n) => [...main.querySelectorAll(`.filters [data-name="${n}"] .dd-o.sel`)].map((o) => o.dataset.v).join(",") || null;
  const sort = picked("sort");
  const f = clear ? {} : { tag: picked("tag"), status: picked("status"), result: picked("result"), automation: picked("automation"), priority: picked("priority") };
  return href("tree", { feature: D.sel, q: D.q || null, ...f, sort: sort === "manual" ? null : sort });
}
function onClick(e) {
  const main = document.getElementById("main");
  const b = e.target.closest("[data-act]");
  if (b && D) {
    const a = b.dataset.act, d = D, ctx = d.ctx;
    if (a === "retry") location.reload();
    else if (a === "clear-filters") location.assign(filterHref(main, true));
    else if (a === "save-desc") {
      const ed = main.querySelector(".fdesc .ed");
      const markdown = ed.classList.contains("src") ? ed.textContent : toMd(ed.innerHTML);
      act(b, main.querySelector(".fdesc"), "Couldn't save the description.", async () => {
        await actions.updateFeature(d.feature.id, { description: { markdown } }, ctx);
        location.replace("#desc-saved");
      });
    } else if (a === "move") {
      const o = main.querySelector('.modal [data-name="dest"] .dd-o.sel'), dest = o ? o.dataset.v : d.move.dest;
      const top = !!main.querySelector('.modal [data-name="at"] [data-v="top"].on');
      const kids = dest === "root" ? MODEL : find(MODEL, dest).node.kids;
      const position = top ? 0 : kids.filter((x) => x.t === "f" && x.id !== d.move.src).length;
      act(b, main.querySelector(".modal .mb"), "Couldn't move the feature.", async () => {
        await actions.moveFeature(d.move.src, dest === "root" ? null : dest, position, ctx);
        location.assign(href("tree", { feature: d.move.src, moved: d.move.src, from: d.move.from, pos: d.move.pos }, "dropped"));
      });
    } else if (a === "undo") {
      const u = d.undo;
      act(b, b.closest(".toast"), "Couldn't undo the move.", async () => {
        if (u.kind === "f") await actions.moveFeature(d.moved, u.from || null, u.pos, ctx);
        else await actions.moveCase(d.moved, u.from, u.pos, ctx);
        location.assign(href("tree", { feature: u.kind === "f" ? d.moved : u.from }));
      });
    }
    return;
  }
  const seg = e.target.closest('.modal [data-name="at"] button');
  if (seg) { seg.parentElement.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === seg)); return; }
  const h = e.target.closest('[data-view="tree"] [data-hash]');
  if (h) { location.hash = h.dataset.hash; return; }
  const tw = e.target.closest("#tree [data-tw]");
  if (tw && CUR) { const x = find(MODEL, tw.closest(".n").dataset.id).node; x.open = !x.open; CUR.model = MODEL; paint(); return; }
  /* a row opens its feature here, or its case in the editor */
  const row = e.target.closest("#tree .n[data-id]");
  if (row && D && !e.target.closest(".gh")) location.assign(row.dataset.t === "f" ? href("tree", { feature: row.dataset.id }) : href("case", { id: row.dataset.id }));
}
function onKey(e) {
  if (!D) return;
  const box = e.target.closest && e.target.closest('[data-view="tree"] .psearch input');
  if (box && e.key === "Enter") { location.assign(href("tree", { feature: D.sel, q: box.value.trim() || null })); return; }
  const input = e.target.closest && e.target.closest('[data-view="tree"] .newrow input');
  if (!input) return;
  if (e.key === "Escape") location.hash = "default";
  if (e.key !== "Enter") return;
  e.preventDefault();
  const d = D;
  input.disabled = true;
  actions.createFeature(input.value.trim(), d.newUnder === "root" ? null : d.newUnder, d.ctx)
    .then((f) => location.assign(href("tree", { feature: f.id })))
    .catch((err) => { showError(document.querySelector("#tcol .tcard"), err, "Couldn't create the feature."); input.disabled = false; });
}
function onPick(e) {
  if (!D || !e.target.closest('[data-view="tree"]')) return;
  const { name: n, value } = e.detail;
  if (n === "product") location.assign(value === "new" ? href("products", { product: null }, "new") : href("tree", { product: value }));
  else if (e.target.closest(".filters")) location.assign(filterHref(document.getElementById("main")));
}
function wire() {
  if (wired) return;
  wired = true;
  document.addEventListener("dragstart", (e) => {
    if (!CUR || !CUR.live) return;
    const n = e.target.closest && e.target.closest('[data-id][draggable="true"]');
    if (!n) return;
    if (KEY) endKeyMove();
    SRC = n.dataset.id;
    e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", SRC);
    requestAnimationFrame(() => n.classList.add("dragging"));
    setBar(`Dragging <b>${esc(name(find(MODEL, SRC).node))}</b> · Esc cancels`);
  });
  document.addEventListener("dragover", (e) => {
    if (!SRC) return;
    const n = e.target.closest && e.target.closest("#tree .n[data-id]");
    clearMarks();
    if (!n || n.dataset.id === SRC) return;
    if (!markDrop(n, SRC, zone(n, e))) { e.dataTransfer.dropEffect = "none"; return; }
    e.preventDefault(); e.dataTransfer.dropEffect = "move";
  });
  document.addEventListener("drop", (e) => {
    if (!SRC) return;
    const n = e.target.closest && e.target.closest("#tree .n[data-id]");
    if (!n || n.dataset.id === SRC) return;
    e.preventDefault();
    const z = zone(n, e);
    if (check(MODEL, SRC, n.dataset.id, z)) return;
    const s = SRC; SRC = null; clearMarks(); setBar(null);
    move(s, n.dataset.id, z);
  });
  document.addEventListener("dragend", () => { clearMarks(); document.querySelectorAll(".dragging").forEach((x) => x.classList.remove("dragging")); if (SRC) setBar(null); SRC = null; });
  document.addEventListener("click", onClick);
  document.addEventListener("keydown", onKey);
  document.addEventListener("keydown", onTreeKey);
  document.addEventListener("dd:change", onPick);
  /* a row focused by pointer becomes the tab stop; focus leaving the tree cancels a keyboard move */
  document.addEventListener("focusin", (e) => { const n = CUR && !KEY && e.target.closest && e.target.closest("#tree .n[data-id]"); if (n) rove(n); });
  document.addEventListener("focusout", (e) => {
    if (!KEY || !(e.target.closest && e.target.closest("#tree"))) return;
    const to = e.relatedTarget;
    if (!(to && to.closest && to.closest("#tree"))) endKeyMove();
  });
}
/* the row a keyboard move or its undo lands on: kept across the reload the server write ends with */
const FOCUS_KEY = "tcms.tree.focus";
function keepFocus(id) { try { sessionStorage.setItem(FOCUS_KEY, id); } catch { /* no storage: focus starts at the tab stop */ } }
function keptFocus() {
  try { const id = sessionStorage.getItem(FOCUS_KEY); sessionStorage.removeItem(FOCUS_KEY); return id; } catch { return null; }
}
/* the tree's keys (WAI-ARIA tree pattern), the keyboard move, and Ctrl+Z for the move toast's Undo */
function onTreeKey(e) {
  if (!CUR) return;
  /* Ctrl+Z undoes a move while its toast is up, except where the field has its own undo */
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "z") {
    const a = document.activeElement, b = document.querySelector('[data-view="tree"] .toast [data-act="undo"]');
    if (b && !b.disabled && D && D.undo && !(a && (a.isContentEditable || a.matches("input, textarea, select")))) {
      e.preventDefault();
      keepFocus(D.moved);
      b.click();
    }
    return;
  }
    const n = e.target.closest && e.target.closest("#tree .n[data-id]");
    if (!n || e.altKey || e.ctrlKey || e.metaKey) return;
    if (KEY) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const i = stepSlot(KEY.sl, KEY.i, e.key === "ArrowDown" ? 1 : -1);
        if (i != null) { KEY.i = i; const s = KEY.sl.list[i], t = rowEl(s.id); clearMarks(); markDrop(t, KEY.src, s.z); focusRow(s.id); }
      } else if (e.key === "Enter") {
        const s = KEY.i == null ? null : KEY.sl.list[KEY.i];
        if (s && !check(MODEL, KEY.src, s.id, s.z)) { const src = endKeyMove(); keepFocus(src); focusRow(src); move(src, s.id, s.z); }
      } else if (e.key === "Escape") focusRow(endKeyMove());
      else if (!["ArrowLeft", "ArrowRight", "Home", "End", " "].includes(e.key)) return;
      e.preventDefault();
      return;
    }
    if (e.key === " ") {
      if (!CUR.live || CUR.ro) return;
      e.preventDefault();
      KEY = { src: n.dataset.id, sl: slots(MODEL, n.dataset.id), i: null };
      n.classList.add("dragging");
      setBar(`Moving <b>${esc(name(find(MODEL, KEY.src).node))}</b> · ↑↓ choose where, Enter drops, Esc cancels`);
      return;
    }
    if (!NAV_KEYS.includes(e.key)) return;
    e.preventDefault();
    const r = navKey(CUR.model, n.dataset.id, e.key);
    if (!r) return;
    if (r.open) location.assign(r.open);
    else if (r.toggle) { const x = find(MODEL, r.toggle).node; x.open = !x.open; CUR.model = MODEL; paint(); focusRow(r.toggle); }
    else focusRow(r.focus);
}

/* ---------- states: ui holds the state's UI options (live drag and drop, open filter, description mode) ---------- */
const S = (ui, extra = {}) => ({ ui, render: (d) => layout(d, ui), ...extra });
const states = {
  "default": S({ live: true }),
  "filters": S({ open: "tag", live: true }),
  "new-feature": { ui: {}, render: (d) => layout(d, { banner: newBanner(d) }) },
  "move": { ui: {}, render: (d) => layout(d, {}) + moveModal(d) },
  "drag-folder-into-folder": S({}),
  "drag-case-reorder": S({}),
  "drag-invalid": S({}),
  "dropped": { ui: { live: true }, render: (d) => layout(d, { live: true }) + droppedToast(d) },
  "empty-product": S({}),
  "loading": { render: loading },
  "error": { render: error },
  "search": S({}),
  "search-empty": S({}),
  "search-cleared": S({ live: true }, { toast: (d) => `<div><b>Search cleared.</b> <span class="muted">Showing all ${d.tree.length} top features in ${esc(d.product.key)}.</span></div>` }),
  "desc-edit": S({ desc: "edit" }),
  "desc-saved": S({ live: true }, { toast: (d) => `<div><b>Description saved.</b></div>` }),
  "desc-agent": S({ live: true }),
  "nav-open": S({}, { navOpen: true }),
  "read-only": S({})
};

export default { nav: "features", default: "default", states,
  /* the tree states keep their model live for drag and drop and the twisties; loading and error have none.
     Every control is one document listener (wire), reading the state on the page from CUR and D. */
  after: (main, id, d) => {
    const s = states[id];
    D = d;
    CUR = s.ui ? opts(d, s.ui) : null;
    MODEL = CUR && CUR.model;
    SRC = null; KEY = null;
    wire();
    const f = CUR && keptFocus();
    if (f) focusRow(f);
  }
};
export const keyboard = { visible, navKey, slots, stepSlot, place, check };
