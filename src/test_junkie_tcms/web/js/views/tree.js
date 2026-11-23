/* Features and cases: one product's feature tree with live drag and drop, the selected feature and its cases. */
import { I, st, ver, dd, esc, bar, psearch, hl, rte, actor, toast, crumbs, lnk, modal } from "../ui.js";

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
  ...d.products.map((p) => ({ v: p.key, label: p.name, short: p.short, hint: p.topFeatures ? `${p.cases} cases · ${p.topFeatures} top features` : "No features yet", icon: `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>` })),
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
    const more = open && x.more && x.kids.some((k) => k.t === "c") ? `<li class="more" style="--d:${d + 1}">+${x.more} more cases · <a href="#">show all</a></li>` : "";
    const add = o.newUnder === x.id ? `<li class="newrow"><div class="n" style="--d:${d + 1}"><span class="gh"></span><span class="tw"></span>${I.folder}<input class="in" value="${esc(o.d.newName)}" aria-label="New feature name" autofocus></div></li>` : "";
    return `<li><div class="${cls}" style="--d:${d}" data-id="${esc(x.id)}" data-t="${x.t}"${o.ro ? "" : ' draggable="true"'} tabindex="0" role="treeitem"${hasK ? ` aria-expanded="${open}"` : ""}>` +
      `${o.ro ? "" : `<span class="gh" title="Drag to move">${I.drag}</span>`}<span class="tw${hasK && !open ? " closed" : ""}"${hasK ? " data-tw" : ""}>${hasK ? I.chevd : ""}</span>${body}<span class="nd" title="Not allowed here">${I.ban}</span></div>` +
      `${o.ext[x.id] || ""}${open || add ? `<ul role="group">${open ? rows(x.kids, d + 1, o) : ""}${more}${add}</ul>` : ""}</li>`;
  }).join("");
}
/* on-page search: keep matches and their ancestors; a matching feature with no matching children stays closed */
function filterModel(list, q) {
  const s = q.toLowerCase();
  return list.map((x) => {
    const hit = (x.t === "c" ? x.key + " " + x.title : x.name).toLowerCase().includes(s);
    const kids = x.kids ? filterModel(x.kids, q) : [];
    if (kids.length) return { ...x, kids, more: 0, open: true };
    if (hit) return x.t === "f" ? { ...x, open: false } : x;
    return null;
  }).filter(Boolean);
}
const hits = (list) => list.reduce((a, x) => a + (x.t === "c" ? 1 : 0) + (x.kids ? hits(x.kids) : 0), 0);
const featHits = (list, q) => list.reduce((a, x) => a + (x.t === "f" && x.name.toLowerCase().includes(q.toLowerCase()) ? 1 : 0) + (x.kids ? featHits(x.kids, q) : 0), 0);
function treeCard(o) {
  const d = o.d;
  let body;
  if (o.emptyProduct) body = '<li class="faint" style="padding:10px 20px;font-size:13px">No features yet</li>';
  else if (o.q && !o.model.length) body = `<li class="tnone"><b>No features or cases match “${esc(o.q)}”</b><span>Search looks at feature names, case keys and case titles in ${esc(d.product.key)}.</span><a href="#search-cleared">Clear search</a></li>`;
  else body = rows(o.model, 0, o);
  const cnt = o.q ? (o.model.length ? `${hits(o.model)} cases · ${o.feats} features` : "0 results") : "";
  return `<div class="card tcard"><div class="hd"><div class="tch"><span class="eyebrow">Product</span>${dd({ value: d.picked, options: prodOpts(d), cls: "sm block", search: "Find a product", label: "Product" })}</div>${o.ro ? "" : `<button class="icon-btn" title="New feature" aria-label="New feature">${I.plus}</button>`}</div>
  ${o.emptyProduct ? "" : psearch({ q: o.q, ph: "Search features and cases", cnt, clear: "#search-cleared" })}
  <div class="dnd-bar${o.barBad ? " bad" : ""}" id="dndbar" role="status"${o.bar ? "" : " hidden"}>${o.bar || ""}</div>
  <ul class="tree" id="tree" role="tree" aria-label="Features and cases">${body}</ul>
  ${o.ro || o.emptyProduct ? "" : `<div class="tfoot">${I.drag}<span>Drag any feature or case. Drop on a feature to put it inside; drop between rows to reorder.</span></div>`}</div>`;
}

/* ---------- case list ---------- */
function casesCard(o) {
  const fe = o.d.feature;
  const f = find(o.model, fe.id);
  const all = f ? f.node.kids.filter((k) => k.t === "c") : [];
  let list = o.filter ? all.filter((c) => o.filter.status.includes(c.life) && o.filter.automation.includes(c.auto)) : all;
  if (o.q) list = list.filter((c) => (c.key + " " + c.title).toLowerCase().includes(o.q.toLowerCase()));
  const tags = (c) => esc(c.tags.map((t) => "#" + t).join(" "));
  const pri = (p) => `<span class="pri"><span class="dot" style="--c:${PRI_COL[p]}"></span>${p}</span>`;
  const rowsH = list.map((c, i) => `<tr class="${c.life === "deprecated" ? "dim" : ""}${i === 0 && !o.filter ? " sel" : ""}" data-id="${esc(c.id)}"${o.ro ? "" : ' draggable="true"'}>
    <td class="g">${o.ro ? "" : `<span class="gh" title="Drag onto a feature">${I.drag}</span>`}</td><td class="key">${esc(c.key)}</td>
    <td class="tt"><a href="${lnk("case.html")}" class="ell" title="${esc(c.title)}">${hl(esc(c.title), o.q)}</a><div class="faint sub"><span class="auto">${AUTO_IC[c.auto]}${c.auto}</span>${pri(c.pri)}${c.tags.length ? `<span>${tags(c)}</span>` : ""}</div></td>
    <td>${ver(c.ver)}</td><td><span class="pill ${c.life}">${c.life}</span></td><td>${st(c.last)}</td></tr>`).join("");
  const mrows = list.map((c) => `<div class="it"><div class="row"><span class="key">${esc(c.key)}</span>${ver(c.ver)}<span class="pill ${c.life}">${c.life}</span>${st(c.last)}</div><a href="${lnk("case.html")}">${esc(c.title)}</a><span class="auto">${AUTO_IC[c.auto]}${c.auto} · ${c.pri}</span></div>`).join("");
  return `<div class="card"><div class="hd"><div class="tch"><span class="eyebrow">${esc(fe.parent)} / ${esc(fe.name)}</span><span class="row">${esc(fe.name)} <span class="faint" style="font-weight:400">${list.length} of ${f ? count(f.node) : 0}</span></span></div>
    <span class="r">${o.ro ? "" : `<button class="btn sm hide-n">${I.cycle}New cycle</button><a class="btn sm primary" href="${lnk("case.html#new-case")}">${I.plus}New case</a>`}</span></div>
    <div class="tbl-wrap mswap"><table class="t"><thead><tr><th></th><th>Key</th><th>Title</th><th>Version</th><th>Status</th><th>Last result</th></tr></thead><tbody>${rowsH}</tbody></table></div>
    <div class="mlist">${mrows}</div></div>`;
}

/* ---------- feature description: people edit it here, agents through MCP features_update (PATCH /features/{id}) ---------- */
function descBlock(o) {
  const fe = o.d.feature;
  const m = o.desc || (fe.agentEdit ? "agent" : "view");
  if (m === "edit") return `<div class="fdesc"><div class="sec-h"><h2>Description</h2></div>
    ${rte({ html: fe.desc, compact: true, focus: true, label: "Feature description", foot: `<span class="faint">Markdown shortcuts work · saves with <code>PATCH /features/${esc(fe.id)}</code></span>` })}
    <div class="row" style="justify-content:flex-end;margin-top:10px"><a class="btn sm" href="#default">Cancel</a><a class="btn sm primary" href="#desc-saved">Save description</a></div></div>`;
  const a = fe.agentEdit;
  const meta = m === "agent"
    ? `<div class="desc-meta agent">${actor("agent", esc(a.agent))}<span>edited via MCP <code>${esc(a.via)}</code> on behalf of</span>${actor("person", a.onBehalfOf)}<span>· ${esc(a.when)}</span><span class="sp"></span><a class="btn sm ghost" href="#desc-agent">View change</a><button class="btn sm">Revert</button></div>`
    : `<div class="desc-meta">${actor("person", fe.edited.by)}<span>edited ${esc(fe.edited.when)}</span></div>`;
  return `<div class="fdesc"><div class="sec-h"><h2>Description</h2>${o.ro ? "" : `<a class="btn sm ghost r" href="#desc-edit">${I.edit}Edit</a>`}</div>
    <div class="rich fd-body">${fe.desc}</div>${meta}</div>`;
}

/* ---------- feature panel: coverage + where the feature is used (release_feature, plan_entry, cycle) ---------- */
function featureCard(o) {
  const fe = o.d.feature;
  const s = fe.stats;
  const L = (h, inner) => `<a class="fx" href="${lnk(h)}">${inner}</a>`;
  return `<div class="card fcard"><div class="hd"><div class="tch"><span class="eyebrow">Feature · ${esc(fe.parent)}</span><span class="row">${I.folder}${esc(fe.name)}</span></div><span class="r faint" style="font-size:12px">owner ${esc(fe.owner)}</span></div>
  <div class="bd">
    ${descBlock(o)}
    <div class="fk"><div><span class="l">Cases</span><b>${s.cases}</b><small>${s.ready} ready · ${s.draft} draft</small></div><div><span class="l">Automated</span><b>${s.automatedPct}%</b><small>${s.automated} of ${s.cases} · ${s.toAutomate} to_automate</small></div><div><span class="l">Ran in ${esc(s.ranIn)}</span><b>${s.ran} of ${s.cases}</b><small>pinned versions</small></div></div>
    <div class="fcov"><span class="l">Latest result per case</span>${bar(fe.latest, "", esc(`${fe.name} · ${s.ranIn}`))}</div>
    <div class="fx-g"><span class="l">In versions</span><div class="fx-r">${fe.versions.map((v) => L(v.href, `${I.tag}<b>${esc(v.ver)}</b><span class="pill ${v.status}">${v.status}</span>`)).join("")}</div></div>
    <div class="fx-g"><span class="l">Used by test plans</span><div class="fx-r">${fe.plans.map((p) => L(p.href, `${I.flag}<b>${esc(p.name)}</b><span class="faint">${esc(p.scope)}</span>`)).join("")}</div></div>
    <div class="fx-g"><span class="l">In cycles</span><div class="fx-r">${fe.cycles.map((c) => L(c.href, `${I.cycle}<b>${esc(c.name)}</b><span class="pill ${c.status}">${c.status}</span>${c.pinned ? `<span class="faint">${c.pinned} pinned</span>` : ""}`)).join("")}</div></div>
  </div></div>`;
}

/* ---------- filters (all dropdowns are dd) ---------- */
function filters(o) {
  const d = o.d, v = o.filter;
  return `<div class="filters">
    ${dd({ multi: true, value: v ? v.tag : [], options: tagOpts(d), search: "Find a tag", pre: "Tag", placeholder: "Any", cls: "sm", w: "170px", open: o.open === "tag", name: "tag", label: "Tag" })}
    ${dd({ multi: true, value: v ? v.status : [], options: OPTS.life, pre: "Status", placeholder: "Any", cls: "sm", w: "184px", name: "status", label: "Status" })}
    ${dd({ multi: true, value: [], options: OPTS.result, pre: "Last result", placeholder: "Any", cls: "sm", w: "170px", name: "result", label: "Last result" })}
    ${dd({ multi: true, value: v ? v.automation : [], options: OPTS.auto, pre: "Automation", placeholder: "Any", cls: "sm", w: "214px", name: "automation", label: "Automation" })}
    ${dd({ multi: true, value: [], options: OPTS.pri, pre: "Priority", placeholder: "Any", cls: "sm hide-n", w: "150px", name: "priority", label: "Priority" })}
    ${v ? '<button class="btn ghost sm">Clear</button>' : ""}<span class="sp"></span>
    ${dd({ value: d.sort, options: OPTS.sort, pre: "Sort", cls: "sm ghost", w: "196px", name: "sort", label: "Sort" })}
  </div>${v ? `<div class="qline mono faint">GET /products/${esc(d.product.key)}/cases?status=${esc(v.status.join(","))}&amp;automation=${esc(v.automation.join(","))}&amp;tag=${esc(v.tag.join(","))}</div>` : ""}`;
}

const head = (d, ro) => `${crumbs([[esc(`${d.product.key} · ${d.product.name}`), "products.html"], ["Features", "tree.html"], [esc(d.feature.parent)], [esc(d.feature.name)]])}
  <div class="ph"><div class="ttl"><span class="eyebrow">Features and cases · ${esc(d.product.key)}</span><h1>Features</h1></div>${ro ? '<span class="chip">viewer · read only</span>' : ""}<div class="actions">${ro ? "" : `<button class="btn hide-n">${I.upload}Import</button><button class="btn">${I.plus}New feature</button>`}</div></div>`;
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
  const o = { ...ui, d, sel: d.sel, q: d.q, filter: d.filter, ro: d.readOnly, newUnder: d.newUnder, emptyProduct: !d.tree.length, model: d.tree, cls: {}, ext: {}, bar: "", barBad: false };
  if (d.move) { o.cls[d.move.src] = "ghost"; o.cls[d.move.dest] = "drop"; }
  if (d.moved) o.cls[d.moved] = "just";
  if (d.drag) dragPreview(o, d.drag);
  if (o.q) { o.feats = featHits(o.model, o.q); o.model = filterModel(o.model, o.q); }
  return o;
}
const right = (o) => {
  if (!o.emptyProduct) return featureCard(o) + casesCard(o);
  const p = o.d.products.find((x) => x.key === o.d.picked);
  return `<div class="card"><div class="empty"><div class="ill">${I.tree}</div><h3>No features in ${esc(p ? p.name : o.d.picked)}</h3><div>Add a feature, then cases under it. Or import from CSV or Markdown.</div><button class="btn primary">${I.plus}New feature</button> <button class="btn">${I.upload}Import</button></div></div>`;
};
function layout(d, ui) {
  const o = opts(d, ui);
  return head(d, o.ro) + (o.banner || "") + filters(o) + `<div class="split"><div id="tcol">${treeCard(o)}</div><div id="ccol">${right(o)}</div></div>`;
}

const newBanner = (d) => `<div class="banner info">${I.info}<div>New feature under <b>${esc(find(d.tree, d.newUnder).node.name)}</b>. Enter saves (<code>features_create</code>), Esc cancels.</div></div>`;
function moveModal(d) {
  const s = find(d.tree, d.move.src).node, t = find(d.tree, d.move.dest).node;
  return modal(`Move '${esc(s.name)}'`,
    `<p style="margin-top:0">Moving <b>${esc(s.name)}</b> (${count(s)} cases) under <b>${esc(t.name)}</b>. Saves with <code>features_move</code>; its cases and their versions move with it.</p>
    <div class="field"><label>Destination feature</label>${dd({ value: d.move.dest, options: destOpts(d), cls: "block", search: "Find a feature", open: true, label: "Destination feature" })}</div>
    <div class="field mb0"><label>Position</label><div class="seg"><button class="on">Inside, at the end</button><button>Inside, at the top</button></div></div>`,
    `<span class="l mono">features_move</span><button class="btn" data-back>Cancel</button><button class="btn primary">Move here</button>`);
}
function droppedToast(d) {
  const m = find(d.tree, d.moved);
  return `<div class="toast" role="status"><div><b>Moved '${esc(name(m.node))}' into '${esc(m.parent ? m.parent.name : d.product.name)}'.</b> <span class="muted">${count(m.node)} cases moved with it · features_move</span></div><button class="btn sm" data-hash="default">Undo</button></div>`;
}
const loading = (d) => head(d) + `<div class="split"><div class="card"><div class="bd stack">${"<span class='skel'></span>".repeat(8)}</div></div><div class="card"><div class="bd stack">${"<span class='skel' style='height:18px'></span>".repeat(6)}</div></div></div>`;
const error = (d) => head(d) + `<div class="banner err">${I.warn}<div style="min-width:0;flex:1"><b>Couldn't load the tree.</b> The server said:
<pre class="raw">${esc(d.error)}</pre></div><div class="r"><button class="btn sm">Retry</button></div></div>`;

/* ---------- live HTML5 drag and drop and twisties (browser only, wired once from after) ---------- */
let CUR = null, MODEL = null, SRC = null, UNDO = null, wired = false;
function paint() {
  const t = document.getElementById("tcol"), c = document.getElementById("ccol");
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
function move(src, tgt, z) {
  UNDO = JSON.parse(JSON.stringify(MODEL));
  const a = find(MODEL, src); a.list.splice(a.i, 1);
  const s = a.node, t = find(MODEL, tgt);
  let dest;
  if (z === "in") {
    const k = t.node.kids, first = k.findIndex((x) => x.t === "c");
    k.splice(s.t === "f" ? (first < 0 ? k.length : first) : k.length, 0, s);
    t.node.open = true; dest = t.node;
  } else { t.list.splice(z === "before" ? t.i : t.i + 1, 0, s); dest = t.parent; }
  CUR = { ...CUR, model: MODEL, cls: { [src]: "just" }, ext: {} };
  paint();
  const dl = dest ? dest.name : CUR.d.product.name;
  toast(`<div><b>Moved '${esc(name(s))}' into '${esc(dl)}'.</b> <span class="muted">${s.t === "f" ? `${count(s)} cases moved with it · features_move` : "Its versions and results stay with it"}</span></div><button class="btn sm" data-undo>Undo</button>`, false, true);
  clearTimeout(move.t); move.t = setTimeout(() => document.querySelectorAll(".toast.live-t").forEach((x) => x.remove()), 7000);
}
function wire() {
  if (wired) return;
  wired = true;
  document.addEventListener("dragstart", (e) => {
    if (!CUR || !CUR.live) return;
    const n = e.target.closest && e.target.closest('[data-id][draggable="true"]');
    if (!n) return;
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
    const z = zone(n, e), why = check(MODEL, SRC, n.dataset.id, z);
    if (why) { n.classList.add("nodrop"); setBar(why, true); e.dataTransfer.dropEffect = "none"; return; }
    e.preventDefault(); e.dataTransfer.dropEffect = "move";
    n.classList.add(z === "in" ? "drop" : z === "before" ? "ins-b" : "ins-a");
    const t = find(MODEL, n.dataset.id);
    setBar(z === "in" ? `Drop into <b>${esc(t.node.name)}</b>${find(MODEL, SRC).node.t === "f" ? ": becomes a sub-feature" : ""}` : `Drop ${z} <b>${esc(name(t.node))}</b> in ${esc(t.parent ? t.parent.name : CUR.d.product.name)}`);
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
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-undo]") && UNDO) {
      MODEL = UNDO; UNDO = null; CUR = { ...CUR, model: MODEL, cls: {} }; paint();
      toast("<div><b>Move undone.</b></div>");
      return;
    }
    const h = e.target.closest('[data-view="tree"] [data-hash]');
    if (h) { location.hash = h.dataset.hash; return; }
    const tw = e.target.closest("#tree [data-tw]");
    if (tw && CUR) { const x = find(MODEL, tw.closest(".n").dataset.id).node; x.open = !x.open; CUR.model = MODEL; paint(); }
  });
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
  "search-cleared": S({ live: true }, { after: (m, d) => toast(`<div><b>Search cleared.</b> <span class="muted">Showing all ${d.tree.length} top features in ${esc(d.product.key)}.</span></div>`) }),
  "desc-edit": S({ desc: "edit" }),
  "desc-saved": S({ live: true }, { after: (m, d) => toast(`<div><b>Description saved.</b> <span class="muted">PATCH /features/${esc(d.feature.id)} · 200</span></div>`) }),
  "desc-agent": S({ live: true }),
  "nav-open": S({}, { navOpen: true }),
  "read-only": S({})
};

export default { nav: "features", default: "default", states,
  /* the tree states keep their model live for drag and drop and the twisties; loading and error have none */
  after: (main, id, d) => {
    const s = states[id];
    CUR = s.ui ? opts(d, s.ui) : null;
    MODEL = CUR && CUR.model;
    SRC = null; UNDO = null;
    wire();
  }
};
