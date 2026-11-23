/* Case editor: one case's steps, rich text and properties, its Markdown view, save outcomes, a new case and the
   read-only view. The data and the writes are data/case.js; a save sends If-Match with the version it loaded, and
   a refused save (409, 422, any other) shows the server's answer raw in place, keeping the edits. */
import { I, ver, actor, dd, rte, toast, toMd, crumbs, esc, person } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions, raw, stepError } from "../data/case.js";

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
  { v: "acceptance", label: "acceptance", hint: "Signed off against a requirement", icon: I.flag },
  { v: "performance", label: "performance", hint: "Speed and load", icon: I.clock },
  { v: "security", label: "security", hint: "Access and data safety", icon: I.key },
  { v: "other", label: "other", hint: "None of the above", icon: I.doc }];
const AUTO_IC = { manual: I.person, automated: I.bolt, to_automate: I.spark };
const AUTO_OPTS = [{ group: "Automation" },
  { v: "manual", label: "manual", hint: "Run by a person in a cycle", icon: AUTO_IC.manual },
  { v: "automated", label: "automated", hint: "Results come from the Test Junkie reporter", icon: AUTO_IC.automated },
  { v: "to_automate", label: "to_automate", hint: "Manual today, queued for automation", icon: AUTO_IC.to_automate }];
const folderOpts = (d) => [{ group: `${d.ctx.product.name} · ${d.ctx.product.key}` },
  ...d.folders.map((f) => ({ v: f.v, label: f.label, short: f.label, hint: f.cases ? `${f.cases} cases` : "Empty", icon: I.folder }))];
const tagOpts = (d) => [{ group: `Tags in ${d.ctx.product.key}` }, ...d.tags.map((t) => ({ v: t.v, label: "#" + t.v, short: t.v, hint: t.cases + " cases", icon: I.tag }))];
const folder = (d) => d.folders.find((f) => f.v === d.case.feature);
const featName = (d) => folder(d).name;
const productCrumb = (d) => [`${esc(d.ctx.product.key)} · ${esc(d.ctx.product.name)}`, href("products", { id: d.ctx.product.key })];
const history = (d) => href("versions", { id: d.case.key });

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
  /* h: { view, id } of the version, plan or cycle */
  const L = (h, inner) => `<a class="fx col" href="${href(h.view, { id: h.id })}">${inner}</a>`;
  const via = { feature: "via feature", case: "picked case" };
  const ctx = `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Where it sits</span><span>Context</span></div></div><div class="bd roomy">
    <div class="path" style="margin-bottom:14px"><a class="pn" href="${href("products", { id: d.ctx.product.key })}">${I.build}${esc(d.ctx.product.key)}</a><span class="pa">${I.chev}</span><a class="pn" href="${href("tree")}">${I.folder}${esc(featName(d))}</a><span class="pa">${I.chev}</span><span class="pn on">${I.doc}${n ? "New case" : esc(c.key)}</span></div>
    ${n ? (c.pickedUpBy.length ? `<p class="muted" style="font-size:12.5px;margin:0">Plans that include ${esc(featName(d))} as a feature pick this case up in their next cycle: ${c.pickedUpBy.map((p) => `${esc(p.name)} (${esc(p.ver)})`).join(", ")}.</p>` : `<p class="muted" style="font-size:12.5px;margin:0">No test plan includes ${esc(featName(d))} as a feature yet.</p>`) : `<div class="fx-g"><span class="l">Versions · release_feature</span><div class="fx-r">${c.versions.map((v) => L(v.href, `${I.tag}<b>${esc(v.ver)}</b><span class="r"><span class="pill ${v.status}">${v.status}</span></span>`)).join("")}</div></div>
    <div class="fx-g"><span class="l">In plans · ${c.plans.length}</span><div class="fx-r">${c.plans.map((p) => L(p.href, `${I.flag}<b>${esc(p.name)}</b><span class="r faint">${via[p.via]}</span>`)).join("")}</div></div>
    <div class="fx-g"><span class="l">In cycles · pinned</span><div class="fx-r">${c.cycles.map((x) => L(x.href, `${I.cycle}<b>${esc(x.name)}</b><span class="r">${ver(x.pin, 1)}</span>`)).join("")}</div></div>`}
  </div></div>`;
  const tags = c.tags.length ? c.tags.map((t) => "#" + esc(t)).join(" ") : '<span class="faint">None</span>';
  const links = c.links.length ? `<div class="row">${c.links.map((l) => `${l.key ? `<span class="chip mono">${esc(l.key)}</span>` : ""}<a class="ell" href="${esc(l.url)}" style="font-size:13px">${esc(l.url)}</a>`).join("")}</div>` : '<span class="faint" style="font-size:13px">None</span>';
  const cur = c.current;
  const pins = n ? [] : cur.pins;
  return `<div class="stack">
  ${ctx}
  <div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Properties</span><span>Details</span></div></div><div class="bd roomy">
    ${fld("Feature", dd({ value: c.feature, options: folderOpts(d), cls: "block", search: "Find a feature", label: "Feature", name: "feature" }), esc(folder(d).path))}
    ${fld("Status", dd({ value: c.status, options: STATUS_OPTS, cls: "block", label: "Status", name: "status" }), `<span class="pill ${c.status}">${c.status}</span>`)}
    ${ro ? fld("Priority", "", `<span class="row">${dot(PRI_COL[c.priority])}${c.priority}</span>`) + fld("Type", "", c.type) : `<div class="grid2">${fld("Priority", dd({ value: c.priority, options: PRI_OPTS, cls: "block", label: "Priority", name: "priority" }))}${fld("Type", dd({ value: c.type, options: TYPE_OPTS, cls: "block", label: "Type", open: o.typeOpen, name: "type" }))}</div>`}
    ${fld("Automation", dd({ value: c.automation, options: AUTO_OPTS, cls: "block", label: "Automation", name: "automation" }), `<span class="auto">${AUTO_IC[c.automation]}${c.automation}</span>`)}
    ${fld("Automation ref", `<div class="in-ic">${I.code}<input id="ar" class="in mono" placeholder="tests/path/test_file.py::Suite::test_name" value="${esc(c.autoRef)}" aria-label="Automation ref"></div><span class="hint">Set when automated; the reporter matches results to the case by this ref.</span>`, c.autoRef ? `<span class="mono">${esc(c.autoRef)}</span>` : '<span class="faint">None</span>')}
    ${fld("Tags", dd({ multi: true, value: c.tags, options: tagOpts(d), cls: "block", search: "Find a tag", placeholder: "No tags", label: "Tags", name: "tags" }), tags)}
    ${ro ? fld("Links", "", c.links.length ? c.links.map((l) => `<a href="${esc(l.url)}">${esc(l.key || l.url)}</a>`).join(" ") : '<span class="faint">None</span>') : `<div class="field mb0"><label>Links</label>
      ${links}
      <div class="grid2" style="margin-top:4px"><input id="lu" class="in" placeholder="URL" aria-label="Link URL"><input id="lk" class="in" placeholder="Key (optional)" aria-label="Link key"></div></div>`}
  </div></div>
  ${n ? "" : `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Version</span><span>Current</span></div><span class="r">${ver(c.version)}</span></div><div class="bd roomy vmeta">
    <div class="row wrap">v${c.version} by ${actor(cur.by.kind, esc(cur.by.name))}</div><div class="muted">${[cur.onBehalf ? `on behalf of ${esc(person(cur.onBehalf)[0])}` : "", cur.via ? `via <span class="via">${esc(cur.via)}</span>` : "", esc(cur.at)].filter(Boolean).join(" · ")}</div>
    <div class="muted">${cur.openCycles ? `Used in ${cur.openCycles} open cycle${cur.openCycles === 1 ? "" : "s"}, pinned at ${pins.map((p) => "v" + p).join(" and ")}.` : "Not in an open cycle."}</div>
    <div><a class="btn sm" href="${history(d)}">${I.restore}History (${c.version})</a></div></div></div>`}
  </div>`;
}

/* o = { ro, md, isNew, typeOpen, focus, banner, extra } */
function editor(d, o = {}) {
  const c = d.case, n = o.isNew, ro = o.ro;
  const t = esc(c.title);
  /* mid-drag the steps show in the dragged order, the lifted step and its drop target marked */
  const list = d.order.length ? d.order.map((id) => c.steps.find((s) => s.id === id)) : c.steps;
  const so = { ro, focus: o.focus, err: d.invalidStep, cls: d.lift != null ? { [d.lift]: "lift", [d.over]: "over" } : null };
  const head = `${crumbs([productCrumb(d), ["Test cases", href("cases")], ...(n ? [["New case"]] : [[esc(c.key), null, "key"]])])}
  <div class="ph"><div class="ttl"><span class="eyebrow">${n ? `New case · ${esc(featName(d))}` : `Case · ${esc(c.key)}`}</span><h1>${n ? "New case" : t}${n ? "" : ver(c.version)}</h1></div>${ro ? '<span class="chip">viewer · read only</span>' : ""}
    <div class="actions">${ro ? `<a class="btn" href="${history(d)}">${I.restore}History</a>` : `
      <div class="seg" role="tablist"><button class="${o.md ? "" : "on"}" data-hash="${n ? "new-case" : "default"}">Editor</button><button class="${o.md ? "on" : ""}" data-hash="markdown"${n ? ' disabled title="Save the case first"' : ""}>${I.md} Markdown</button></div>
      ${n ? "" : `<a class="btn hide-n" href="${history(d)}">${I.restore}History</a>`}`}</div></div>`;
  /* the Markdown file is one pre block that fills the column */
  const body = o.md ? `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Markdown</span><span>${esc(c.key)}.md</span></div><span class="r faint" style="font-size:12px">Import and export as Markdown; stored as rich-text JSON. Raw HTML is refused.</span></div><div class="bd roomy">
    <div class="rte mdbox"><div class="rtb" role="toolbar" aria-label="Markdown file"><span class="mdhead">${I.doc}<span class="mono">${esc(c.key)}.md</span></span><span class="sp"></span><button type="button" title="Copy" aria-label="Copy" data-act="copy">${I.copy}</button><button type="button" title="Import a .md file" aria-label="Import" data-act="import">${I.upload}</button><button type="button" class="mdt on" aria-pressed="true">${I.md}<span>MD</span></button><input type="file" accept=".md,text/markdown,text/plain" hidden data-import></div>
    <pre class="ed src mdsrc" contenteditable="true" spellcheck="false" aria-label="Markdown source" style="display:block;margin:0;width:100%;box-sizing:border-box">${esc(c.md)}</pre></div>
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
    <div class="field mb0" style="flex:1;min-width:200px"><input id="cn" class="in" aria-label="Change note" placeholder="Change note (optional)" value="${o.md ? "" : esc(c.changeNote)}"></div>
    ${n ? "" : `<span class="faint mono hide-n" style="font-size:11.5px">If-Match: "v${c.version}"</span>`}
    <button class="btn" data-act="cancel">Cancel</button><button class="btn primary" data-act="${n ? "create" : o.md ? "save-md" : "save"}">${n ? (c.key ? `Create ${esc(c.key)} as v1` : "Create as v1") : `Save as v${c.version + 1}`}</button></div>`;
  return head + (o.banner || "") + `<div class="split r"><div>${body}${foot}</div>${side(d, o)}</div>` + (o.extra || "");
}

const reorderBanner = (d) => `<div class="banner info">${I.info}<div>Dragging step <b>${esc(d.order[d.lift])}</b> above <b>${esc(d.order[d.over])}</b>. Step ids stay with the step, so results and the v${d.case.version}→v${d.case.version + 1} diff follow it. Keyboard: focus a step, Alt+↑/↓.</div></div>`;
/* savedAs: the version the save made (the page loads it again after a save) */
const savedToast = (d) => `<div class="toast" role="status"><div><b>Saved ${esc(d.case.key)} as v${d.savedAs}.</b> <span class="muted">${d.case.current.pins.length ? `Open cycles keep their pinned versions (${d.case.current.pins.map((p) => "v" + p).join(", ")}).` : "No open cycle pins this case."}</span></div><a class="btn sm" href="${href("versions", { id: d.case.key }, "compare")}">View diff</a></div>`;
const conflictBanner = (d) => `<div class="banner err" data-err>${I.warn}<div style="flex:1;min-width:0"><b>Not saved: ${esc(d.case.key)} changed since you opened it.</b> Your edits are kept here.
<pre class="raw">${esc(d.error)}</pre></div><div class="r"><a class="btn sm" href="${href("versions", { id: d.case.key }, "compare")}">Compare with v${d.currentVersion}</a><button class="btn sm primary" data-act="reapply">Reload and reapply</button></div></div>`;
const FIELD = { action: "action", expected: "expected result" };
const invalidBanner = (d) => `<div class="banner err" data-err>${I.warn}<div style="flex:1;min-width:0"><b>Not saved.</b> The server refused step ${d.invalidStep + 1}'s ${FIELD[d.invalidField] || "expected result"}:
<pre class="raw">${esc(d.error)}</pre></div></div>`;

/* ---------- the writes: what the page holds, sent through data/case.js ---------- */
const val = (main, id) => { const x = main.querySelector("#" + id); return x ? x.value.trim() : ""; };
const picks = (main, name) => [...main.querySelectorAll(`.dd[data-name="${name}"] .dd-o.sel`)].map((o) => o.dataset.v).filter(Boolean);
/* an editor's Markdown when the user changed it, else null (a save sends the stored Markdown back as it was) */
function mdOf(r) {
  if (!r || !r.dataset.dirty) return null;
  const ed = r.querySelector(".ed");
  return ed.classList.contains("src") ? ed.textContent : toMd(ed.innerHTML);
}
const rteOf = (el, label) => { const ed = el && el.querySelector(`.ed[aria-label="${label}"]`); return ed && ed.closest("[data-rte]"); };
function editOf(main, d) {
  const c = d.case;
  const one = (name, was) => picks(main, name)[0] || was;
  const url = val(main, "lu");
  return {
    title: val(main, "ti"),
    desc: mdOf(rteOf(main, "Description")), pre: mdOf(rteOf(main, "Preconditions")),
    steps: [...main.querySelectorAll("#steps .step")].map((s) => ({
      id: c.src && c.src.steps[s.dataset.id] ? s.dataset.id : "",
      action: mdOf(s.querySelector(".ac [data-rte]")), expected: mdOf(s.querySelector(".ex [data-rte]"))
    })),
    feature: one("feature", c.feature), status: one("status", c.status), priority: one("priority", c.priority),
    type: one("type", c.type), automation: one("automation", c.automation), autoRef: val(main, "ar"),
    tags: picks(main, "tags"),
    links: [...c.links, ...(url ? [{ url, key: val(main, "lk") }] : [])],
    changeNote: val(main, "cn")
  };
}
/* show the saved case: a load of #saved (a reload when the page is already there) */
const toSaved = (key) => {
  const to = href("case", { id: key }, "saved");
  if (location.search + location.hash === to) location.reload(); else location.assign(to);
};
/* a refused save, raw and in place, the edits kept: 409 offers a reapply on the current version, a 422 on a
   step marks that step, anything else is the server's answer as is */
function failed(main, e) {
  main.querySelectorAll("[data-err], .serr").forEach((x) => x.remove());
  const b = (e && e.body) || {};
  const ph = main.querySelector(".ph");
  if (e && e.status === 409 && b.current_version != null) {
    live.currentVersion = b.current_version;
    ph.insertAdjacentHTML("afterend", conflictBanner({ case: live.d.case, error: raw(e), currentVersion: b.current_version }));
    return;
  }
  const bad = stepError(e);
  if (bad) {
    const { i, field } = bad;
    ph.insertAdjacentHTML("afterend", invalidBanner({ invalidStep: i, invalidField: field, error: raw(e) }));
    const s = main.querySelectorAll("#steps .step")[i];
    const cell = s && s.querySelector(field === "action" ? ".ac" : ".ex");
    if (cell) cell.insertAdjacentHTML("beforeend", `<div class="serr">${I.warn}<span>Refused by the server. Fix this ${FIELD[field]} and save again.</span></div>`);
    return;
  }
  showError(main.querySelector(".split.r > div"), e, "Couldn't save the case.");
}
async function write(main, btn, version) {
  const d = live.d;
  btn.disabled = true;
  try {
    if (live.state === "new-case") {
      const made = await actions.create(editOf(main, d), d.ctx);
      location.assign(href("case", { id: made.key }, "saved"));
    } else if (live.state === "markdown") {
      const out = await actions.saveMarkdown(d.case, main.querySelector(".mdsrc").textContent, val(main, "cn"), d.ctx, version);
      toSaved(out.key);
    } else {
      const out = await actions.save(d.case, editOf(main, d), d.ctx, version);
      toSaved(out.key);
    }
  } catch (e) {
    failed(main, e);
    btn.disabled = false;
  }
}
function act(main, b) {
  const a = b.dataset.act, d = live.d;
  if (a === "save" || a === "save-md" || a === "create") return write(main, b, d.case.version);
  if (a === "reapply") return write(main, main.querySelector(".runfoot .btn.primary"), live.currentVersion);
  if (a === "cancel") return location.assign(live.state === "new-case" ? href("cases") : href("case", { id: d.case.key }));
  if (a === "copy") {
    return navigator.clipboard.writeText(main.querySelector(".mdsrc").textContent)
      .then(() => toast(`<div><b>Copied ${esc(d.case.key)}.md.</b></div>`), (e) => showError(main.querySelector(".split.r > div"), e, "Couldn't copy."));
  }
  if (a === "import") main.querySelector("[data-import]").click();
}

/* live: drag a step by its grip, Alt+arrows, add and delete steps, and the writes. Wired once per page on main;
   live holds the shown state and its data. */
let live = { ro: false, saveAs: 0, state: "", d: null, currentVersion: null };
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
  // an editor the user typed in sends its new Markdown on save; the others send what is stored
  main.addEventListener("input", (e) => { const r = e.target.closest && e.target.closest("[data-rte]"); if (r) r.dataset.dirty = "1"; });
  main.addEventListener("change", async (e) => {
    if (!e.target.matches("[data-import]") || !e.target.files.length) return;
    main.querySelector(".mdsrc").textContent = await e.target.files[0].text();
    e.target.value = "";
  });
  main.addEventListener("click", (e) => {
    const b = e.target.closest("[data-act]");
    if (b && live.d && !b.disabled) { act(main, b); return; }
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
    live = { ro: id === "viewer", saveAs: d.case.version + 1, state: id, d, currentVersion: null };
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
