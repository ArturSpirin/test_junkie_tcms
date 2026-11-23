/* Case editor: one case's steps, rich text and properties, its Markdown view, save outcomes, a new case and the read-only view. */
import { I, ver, actor, dd, rte, toast, crumbs, lnk, esc, person } from "../ui.js";

/* fixed choices of the case model (UI copy); features and tags come from data */
const STATUS_OPTS = [{ group: "Case status" },
  { v: "draft", label: "draft", hint: "Work in progress", dot: "var(--faint)" },
  { v: "ready", label: "ready", hint: "Can be added to cycles", dot: "var(--pass)" },
  { v: "deprecated", label: "deprecated", hint: "Kept for history, not added to new cycles", dot: "var(--untested)" }];
const PRI_COL = { critical: "var(--fail)", high: "var(--blocked)", medium: "var(--retest)", low: "var(--faint)" };
const PRI_HINT = { critical: "Blocks a release", high: "Run in every cycle", medium: "Run when the area changes", low: "Run before major releases" };
const PRI_OPTS = [{ group: "Priority" }, ...Object.keys(PRI_HINT).map((v, i) => ({ v, label: v, hint: PRI_HINT[v], dot: PRI_COL[v], kbd: String(i + 1) }))];
const TYPE_OPTS = [{ group: "Case type" },
  { v: "functional", label: "functional", hint: "One behaviour, end to end", icon: I.check },
  { v: "regression", label: "regression", hint: "Guards a fixed bug", icon: I.restore },
  { v: "smoke", label: "smoke", hint: "Fast check that the build is usable", icon: I.bolt },
  { v: "acceptance", label: "acceptance", hint: "Signed off against a requirement", icon: I.flag }];
const AUTO_IC = { manual: I.person, automated: I.bolt, to_automate: I.spark };
const AUTO_OPTS = [{ group: "Automation" },
  { v: "manual", label: "manual", hint: "Run by a person in a cycle", icon: AUTO_IC.manual },
  { v: "automated", label: "automated", hint: "Results come from the Test Junkie reporter", icon: AUTO_IC.automated },
  { v: "to_automate", label: "to_automate", hint: "Manual today, queued for automation", icon: AUTO_IC.to_automate }];
const folderOpts = (d) => [{ group: `${d.ctx.product.name} · ${d.ctx.product.key}` },
  ...d.folders.map((f) => ({ v: f.v, label: f.label, short: f.label, hint: f.cases ? `${f.cases} cases` : "Empty", icon: I.folder }))];
const tagOpts = (d) => [{ group: `Tags in ${d.ctx.product.key}` }, ...d.tags.map((t) => ({ v: t.v, label: "#" + t.v, short: t.v, hint: t.cases + " cases", icon: I.tag }))];
const folder = (d) => d.folders.find((f) => f.v === d.case.feature);
const featName = (d) => folder(d).label.split(" / ").pop();
const productCrumb = (d) => [`${esc(d.ctx.product.key)} · ${esc(d.ctx.product.name)}`, "products.html#detail"];

/* the step list; o = { ro, cls: {index: class}, focus: "a0" | "e2", err: index } */
function steps(o, list) {
  const ro = o.ro;
  return `<div class="step-hd"><span></span><span>#</span><span>Action</span><span>Expected result</span><span></span></div><div class="steps" id="steps">` +
    list.map((s, i) => `<div class="step ${(o.cls && o.cls[i]) || ""}" data-id="${esc(s.id)}">
      <span class="grip"${ro ? "" : ' data-grip title="Drag to reorder (or Alt+↑/↓)"'}>${ro ? "" : I.grip}</span><span class="no">${o.cls && o.cls[i] === "lift" ? `<span class="disc cur">${i + 1}</span>` : `<span>${i + 1}</span>`}</span>
      <div class="ac"><span class="mini-lbl">Action</span>${rte({ html: s.action, compact: true, ro, placeholder: "What the tester does", label: `Step ${i + 1} action`, focus: o.focus === "a" + i })}<span class="sid">${esc(s.id)}</span></div>
      <div class="ex"><span class="mini-lbl">Expected result</span>${rte({ html: s.expected, compact: true, ro, placeholder: "What should happen", label: `Step ${i + 1} expected result`, focus: o.focus === "e" + i })}${o.err === i ? `<div class="serr">${I.warn}<span>Refused by the server: raw HTML isn't allowed here. Use the toolbar or Markdown.</span></div>` : ""}</div>
      <span class="del">${ro ? "" : `<button class="icon-btn" data-del aria-label="Delete step ${i + 1}">${I.trash}</button>`}</span></div>`).join("") +
    `</div>${ro ? "" : `<div class="row wrap addrow"><button class="btn sm" data-add>${I.plus}Add step</button><span class="faint hide-n" style="font-size:12px">Alt+↑/↓ moves the focused step</span></div>`}`;
}

function side(d, o) {
  const c = d.case, n = o.isNew, ro = o.ro;
  const fld = (label, ctl, roText, cls = "") => ro ? `<div class="kv"><span class="eyebrow">${label}</span><span>${roText}</span></div>` : `<div class="field ${cls}"><label>${label}</label>${ctl}</div>`;
  const dot = (col) => `<span class="dot" style="--c:${col}"></span>`;
  const L = (h, inner) => `<a class="fx col" href="${lnk(h)}">${inner}</a>`;
  const via = { feature: "via feature", case: "picked case" };
  const ctx = `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Where it sits</span><span>Context</span></div></div><div class="bd roomy">
    <div class="path" style="margin-bottom:14px"><a class="pn" href="${lnk("products.html#detail")}">${I.build}${esc(d.ctx.product.key)}</a><span class="pa">${I.chev}</span><a class="pn" href="${lnk("tree.html")}">${I.folder}${esc(featName(d))}</a><span class="pa">${I.chev}</span><span class="pn on">${I.doc}${n ? "New case" : esc(c.key)}</span></div>
    ${n ? `<p class="muted" style="font-size:12.5px;margin:0">Plans that include ${esc(featName(d))} as a feature pick this case up in their next cycle: ${c.pickedUpBy.map((p) => `${esc(p.name)} (${esc(p.ver)})`).join(", ")}.</p>` : `<div class="fx-g"><span class="l">Versions · release_feature</span><div class="fx-r">${c.versions.map((v) => L(v.href, `${I.tag}<b>${esc(v.ver)}</b><span class="r"><span class="pill ${v.status}">${v.status}</span></span>`)).join("")}</div></div>
    <div class="fx-g"><span class="l">In plans · ${c.plans.length}</span><div class="fx-r">${c.plans.map((p) => L(p.href, `${I.flag}<b>${esc(p.name)}</b><span class="r faint">${via[p.via]}</span>`)).join("")}</div></div>
    <div class="fx-g"><span class="l">In cycles · pinned</span><div class="fx-r">${c.cycles.map((x) => L(x.href, `${I.cycle}<b>${esc(x.name)}</b><span class="r">${ver(x.pin, 1)}</span>`)).join("")}</div></div>`}
  </div></div>`;
  const tags = c.tags.length ? c.tags.map((t) => "#" + esc(t)).join(" ") : '<span class="faint">None</span>';
  const links = c.links.length ? `<div class="row">${c.links.map((l) => `<span class="chip mono">${esc(l.key)}</span><a class="ell" href="#" style="font-size:13px">${esc(l.url)}</a>`).join("")}</div>` : '<span class="faint" style="font-size:13px">None</span>';
  const cur = c.current;
  return `<div class="stack">
  ${ctx}
  <div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Properties</span><span>Details</span></div></div><div class="bd roomy">
    ${fld("Feature", dd({ value: c.feature, options: folderOpts(d), cls: "block", search: "Find a feature", label: "Feature" }), esc(folder(d).label.split(" / ").join(" › ")))}
    ${fld("Status", dd({ value: c.status, options: STATUS_OPTS, cls: "block", label: "Status" }), `<span class="pill ${c.status}">${c.status}</span>`)}
    ${ro ? fld("Priority", "", `<span class="row">${dot(PRI_COL[c.priority])}${c.priority}</span>`) + fld("Type", "", c.type) : `<div class="grid2">${fld("Priority", dd({ value: c.priority, options: PRI_OPTS, cls: "block", label: "Priority" }))}${fld("Type", dd({ value: c.type, options: TYPE_OPTS, cls: "block", label: "Type", open: o.typeOpen }))}</div>`}
    ${fld("Automation", dd({ value: c.automation, options: AUTO_OPTS, cls: "block", label: "Automation" }), `<span class="auto">${AUTO_IC[c.automation]}${c.automation}</span>`)}
    ${fld("Automation ref", `<div class="in-ic">${I.code}<input class="in mono" placeholder="tests/path/test_file.py::Suite::test_name" value="${esc(c.autoRef)}" aria-label="Automation ref"></div><span class="hint">Set when automated; the reporter matches results to the case by this ref.</span>`, c.autoRef ? `<span class="mono">${esc(c.autoRef)}</span>` : '<span class="faint">None</span>')}
    ${fld("Tags", dd({ multi: true, value: c.tags, options: tagOpts(d), cls: "block", search: "Find or add a tag", placeholder: "No tags", label: "Tags" }), tags)}
    ${ro ? fld("Links", "", c.links.map((l) => `<a href="#">${esc(l.key)}</a>`).join(" ")) : `<div class="field mb0"><label>Links</label>
      ${links}
      <div class="grid2" style="margin-top:4px"><input class="in" placeholder="URL" aria-label="Link URL"><input class="in" placeholder="Key (optional)" aria-label="Link key"></div></div>`}
  </div></div>
  ${n ? "" : `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Version</span><span>Current</span></div><span class="r">${ver(c.version)}</span></div><div class="bd roomy vmeta">
    <div class="row wrap">v${c.version} by ${actor(cur.by.kind, esc(cur.by.name))}</div><div class="muted">on behalf of ${esc(person(cur.onBehalf)[0])} · via <span class="via">${esc(cur.via)}</span> · ${esc(cur.at)}</div>
    <div class="muted">Used in ${cur.openCycles} open cycles, pinned at ${cur.pins.map((p) => "v" + p).join(" and ")}.</div>
    <div><a class="btn sm" href="${lnk("versions.html")}">${I.restore}History (${c.version})</a></div></div></div>`}
  </div>`;
}

/* o = { ro, md, isNew, typeOpen, focus, banner, extra } */
function editor(d, o = {}) {
  const c = d.case, n = o.isNew, ro = o.ro;
  const t = esc(c.title);
  /* mid-drag the steps show in the dragged order, the lifted step and its drop target marked */
  const list = d.order.length ? d.order.map((id) => c.steps.find((s) => s.id === id)) : c.steps;
  const so = { ro, focus: o.focus, err: d.invalidStep, cls: d.lift != null ? { [d.lift]: "lift", [d.over]: "over" } : null };
  const head = `${crumbs([productCrumb(d), ["Test cases", "cases.html"], ...(n ? [["New case"]] : [[esc(c.key), null, "key"]])])}
  <div class="ph"><div class="ttl"><span class="eyebrow">${n ? `New case · ${esc(featName(d))}` : `Case · ${esc(c.key)}`}</span><h1>${n ? "New case" : t}${n ? "" : ver(c.version)}</h1></div>${ro ? '<span class="chip">viewer · read only</span>' : ""}
    <div class="actions">${ro ? `<a class="btn" href="${lnk("versions.html")}">${I.restore}History</a>` : `
      <div class="seg" role="tablist"><button class="${o.md ? "" : "on"}" data-hash="${n ? "new-case" : "default"}">Editor</button><button class="${o.md ? "on" : ""}" data-hash="markdown">${I.md} Markdown</button></div>
      ${n ? "" : `<a class="btn hide-n" href="${lnk("versions.html")}">${I.restore}History</a>`}`}</div></div>`;
  const body = o.md ? `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Markdown</span><span>${esc(c.key)}.md</span></div><span class="r faint" style="font-size:12px">Import and export as Markdown; stored as rich-text JSON. Raw HTML is refused.</span></div><div class="bd roomy">
    <div class="rte mdbox"><div class="rtb" role="toolbar" aria-label="Markdown file"><span class="mdhead">${I.doc}<span class="mono">${esc(c.key)}.md</span></span><span class="sp"></span><button type="button" title="Copy" aria-label="Copy">${I.copy}</button><button type="button" title="Import a .md file" aria-label="Import">${I.upload}</button><button type="button" class="mdt on" aria-pressed="true">${I.md}<span>MD</span></button></div>
    <div class="ed rich src" contenteditable="true" spellcheck="false" aria-label="Markdown source">${esc(c.md)}</div></div>
    <div class="muted" style="font-size:12px;margin-top:10px">Step id comments keep results and diffs tied to the same step after a reorder. A step without one gets a new id.</div></div></div>`
  : `<div class="stack"><div class="card"><div class="bd roomy">
    ${ro ? `<div class="sec"><span class="eyebrow">Title</span><h2>${t}</h2></div>` : `<div class="field"><label for="ti">Title</label><input id="ti" class="in title" value="${t}" placeholder="What the case checks"></div>`}
    <div class="field"><label>Description</label>${rte({ html: c.desc, ro, placeholder: "What this case checks and why", label: "Description" })}</div>
    <div class="field mb0"><label>Preconditions <span class="muted">optional</span></label>${rte({ html: c.pre, ro, placeholder: "State the system must be in before step 1", label: "Preconditions" })}</div>
  </div></div>
  <div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Steps</span><span>${list.length === 1 ? "1 step" : list.length + " steps"}</span></div><span class="r faint" style="font-size:12px">${ro ? "" : "drag the grip to reorder"}</span></div><div class="bd roomy">
    ${steps(so, list)}
  </div></div></div>`;
  const foot = ro ? "" : `<div class="runfoot">
    <div class="field mb0" style="flex:1;min-width:200px"><input class="in" aria-label="Change note" placeholder="Change note (optional)" value="${o.md ? "" : esc(c.changeNote)}"></div>
    ${n ? "" : `<span class="faint mono hide-n" style="font-size:11.5px">If-Match: "v${c.version}"</span>`}
    <button class="btn">Cancel</button><button class="btn primary">${n ? `Create ${esc(c.key)} as v1` : `Save as v${c.version + 1}`}</button></div>`;
  return head + (o.banner || "") + `<div class="split r"><div>${body}${foot}</div>${side(d, o)}</div>` + (o.extra || "");
}

const reorderBanner = (d) => `<div class="banner info">${I.info}<div>Dragging step <b>${esc(d.order[d.lift])}</b> above <b>${esc(d.order[d.over])}</b>. Step ids stay with the step, so results and the v${d.case.version}→v${d.case.version + 1} diff follow it. Keyboard: focus a step, Alt+↑/↓.</div></div>`;
const savedToast = (d) => `<div class="toast" role="status"><div><b>Saved ${esc(d.case.key)} as v${d.case.version + 1}.</b> <span class="muted">Open cycles keep their pinned versions (${d.case.current.pins.map((p) => "v" + p).join(", ")}).</span></div><a class="btn sm" href="${lnk("versions.html")}">View diff</a></div>`;
const conflictBanner = (d) => `<div class="banner err">${I.warn}<div style="flex:1;min-width:0"><b>Not saved: ${esc(d.case.key)} changed since you opened it.</b> Your edits are kept here.
<pre class="raw">${esc(d.error)}</pre></div><div class="r"><a class="btn sm" href="${lnk("versions.html")}">Compare with v${d.currentVersion}</a><button class="btn sm primary">Reload and reapply</button></div></div>`;
const invalidBanner = (d) => `<div class="banner err">${I.warn}<div style="flex:1;min-width:0"><b>Not saved.</b> The server refused step ${d.invalidStep + 1}'s expected result:
<pre class="raw">${esc(d.error)}</pre></div></div>`;

/* live: drag a step by its grip, Alt+arrows, add and delete steps. Wired once per page on main; live holds the shown state. */
let live = { ro: false, saveAs: 0 };
let DRAG = null, NEWN = 1;
function wire(main) {
  const box = () => main.querySelector("#steps");
  const renum = () => { const b = box(); if (b) b.querySelectorAll(".step").forEach((s, i) => { s.querySelector(".no").innerHTML = `<span>${i + 1}</span>`; }); };
  const clearOver = () => main.querySelectorAll("#steps .over").forEach((x) => x.classList.remove("over"));
  main.addEventListener("mousedown", (e) => { const g = e.target.closest("[data-grip]"); if (g) g.closest(".step").draggable = true; });
  main.addEventListener("dragstart", (e) => {
    const s = e.target.closest && e.target.closest(".step");
    if (!s || !s.draggable) return;
    DRAG = s; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", s.dataset.id);
    requestAnimationFrame(() => s.classList.add("dragging"));
  });
  main.addEventListener("dragover", (e) => {
    if (!DRAG) return;
    const t = e.target.closest && e.target.closest("#steps .step");
    clearOver();
    if (t && t !== DRAG) { e.preventDefault(); t.classList.add("over"); }
  });
  main.addEventListener("drop", (e) => {
    if (!DRAG) return;
    const t = e.target.closest && e.target.closest("#steps .step");
    if (!t || t === DRAG) return;
    e.preventDefault(); box().insertBefore(DRAG, t); renum();
    toast(`<div><b>Moved step ${esc(DRAG.dataset.id)}</b> <span class="muted">to position ${[...box().children].indexOf(DRAG) + 1}. Its id stays with it.</span></div>`);
  });
  main.addEventListener("dragend", () => {
    if (DRAG) { DRAG.classList.remove("dragging"); DRAG.draggable = false; DRAG = null; }
    clearOver(); renum();
  });
  main.addEventListener("keydown", (e) => {
    const s = e.target.closest && e.target.closest("#steps .step");
    if (!s || !e.altKey || live.ro) return;
    const b = box();
    if (e.key === "ArrowUp" && s.previousElementSibling) { b.insertBefore(s, s.previousElementSibling); e.preventDefault(); renum(); }
    if (e.key === "ArrowDown" && s.nextElementSibling) { b.insertBefore(s.nextElementSibling, s); e.preventDefault(); renum(); }
  });
  main.addEventListener("click", (e) => {
    if (e.target.closest("[data-add]")) {
      const b = box(), i = b.children.length;
      const tmp = document.createElement("div");
      tmp.innerHTML = steps({ focus: "a" + i }, [{ id: "st_new" + NEWN++, action: "", expected: "" }]);
      const s = tmp.querySelector(".step");
      b.appendChild(s); renum();
      const ed = s.querySelector(".ed"); if (ed) ed.focus();
      return;
    }
    const del = e.target.closest("[data-del]");
    if (del) { const s = del.closest(".step"); const id = s.dataset.id; s.remove(); renum(); toast(`<div><b>Deleted step ${esc(id)}.</b> <span class="muted">Saved when you save v${live.saveAs}.</span></div>`); }
  });
}

export default { nav: "cases", default: "default",
  after: (main, id, d) => {
    main.querySelectorAll("[data-hash]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.hash; }));
    live = { ro: id === "viewer", saveAs: d.case.version + 1 };
    if (!main.dataset.stepsLive) { main.dataset.stepsLive = "1"; wire(main); }
  },
  states: {
    "default": { render: (d) => editor(d, { focus: "e2" }) },
    "reorder": { render: (d) => editor(d, { banner: reorderBanner(d) }) },
    "markdown": { render: (d) => editor(d, { md: true }) },
    "saved": { render: (d) => editor(d) + savedToast(d) },
    "conflict-409": { render: (d) => editor(d, { banner: conflictBanner(d) }) },
    "invalid-422": { render: (d) => editor(d, { focus: "e2", banner: invalidBanner(d) }) },
    "new-case": { render: (d) => editor(d, { isNew: true, typeOpen: true, focus: "a0" }) },
    "viewer": { render: (d) => editor(d, { ro: true }) }
  }
};
