/* Test plans: the product's plan list, one plan's detail, the new-plan and edit-entries forms and making a cycle.
   The data and the writes are data/plans.js; the list's name search is the server's (the view never searches). */
import { I, bar, crumbs, modal, dd, tg, ver, psearch, hl, esc } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions, parseQuery } from "../data/plans.js";

const pillOf = (s) => `<span class="pill ${s === "archived" ? "closed" : s}">${s}</span>`;
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const prodOf = (d) => d.product || d.ctx.product;
const prodLabel = (d) => `${esc(prodOf(d).key)} · ${esc(prodOf(d).name)}`;
const at = (d) => ({ product: prodOf(d).key });
const prodHref = (d) => href("products", { ...at(d), id: prodOf(d).key });
const mark = (p) => `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>`;
const listHead = (d) => head("Test plans", `Planning · ${prodLabel(d)}`, crumbs([[prodLabel(d), prodHref(d)], ["Test plans"]]), `<a class="btn primary" href="#new">${I.plus}New plan</a>`);
const STATUS_OPTS = [{ v: "draft", label: "draft", dot: "var(--faint)" }, { v: "active", label: "active", dot: "var(--pass)" }, { v: "archived", label: "archived", dot: "var(--muted)" }];
const filters = (d) => `<div class="row wrap" style="gap:10px;margin-bottom:16px">${dd({ value: d.versionFilter, options: [{ v: "all", label: "All versions" }, "-", { group: `${d.ctx.product.key} versions` }, ...d.ctx.versions.map((v) => ({ v: v.ver, label: v.ver, hint: v.status, icon: I.tag }))], pre: "Version", cls: "sm", w: "190px", label: "Version", name: "fver" })}${dd({ multi: true, value: d.statusFilter, options: STATUS_OPTS, pre: "Status", cls: "sm", w: "200px", label: "Status", name: "fstatus" })}</div>`;
const cleared = () => href("plans", {}, "search-cleared");
const S = (q, cnt) => psearch({ q, ph: "Search plans by name", cnt, clear: cleared() });
/* d.plans is what the server matched for d.q (plans_list?q=), with the version and status filters; d.total counts every plan */
const list = (d) => {
  const q = d.q, hits = d.plans, key = esc(d.ctx.product.key);
  const rowsH = hits.map((p) => `<a class="pl" href="${href("plans", { ...at(d), id: p.id })}"><div class="n"><b class="ell">${hl(esc(p.name), q)}</b><small>${esc(p.scope)} · ${esc(p.cases)}</small></div><div>${pillOf(p.status)}</div><span class="s row">${I.tag}${esc(p.version)}</span>${Object.keys(p.results).length ? bar(p.results, "", esc(p.name) + " · last cycle") : '<span class="faint" style="font-size:12px">no cycle yet</span>'}</a>`).join("");
  const body = hits.length ? rowsH : `<div class="empty"><div class="ill">${I.search}</div><h3>No plans match “${esc(q)}”</h3><p class="muted" style="margin:0 auto 14px;max-width:420px">Search looks at plan names. Try another word, or clear the filters.</p><a class="btn" href="${cleared()}">Clear search</a> <a class="btn primary" href="#new">${I.plus}New plan</a></div>`;
  return listHead(d) + `<div class="sub">A plan says <b>what</b> to test for a version: whole features, single cases, or a query. Each cycle made from it pins the cases it resolves to.</div>` +
    S(q, hits.length + (hits.length === 1 ? " plan" : " plans")) + filters(d) +
    `<div class="card"><div class="hd"><h2>Plans in ${key}</h2><span class="r faint" style="font-size:12px">${hits.length} of ${d.total}</span></div>${body}</div>`;
};

const KIND_ICON = { feature: I.folder, query: I.filter, case: I.doc };
const entryRow = (e, edit) => `<div class="src"${e.id ? ` data-id="${esc(e.id)}"` : ""}${e.add ? ` data-add="${esc(JSON.stringify(e.add))}"` : ""}><span class="ic">${KIND_ICON[e.kind]}</span><div style="min-width:0"><div class="t1">${esc(e.label)}</div><div class="t2">${esc(e.meta)}</div></div><span class="r"><span class="kind">${e.kind}</span>${edit ? `<button class="icon-btn" aria-label="Remove" data-remove>${I.x}</button>` : ""}</span></div>`;
const entries = (d, edit) => `<div data-entries>${d.detail.entries.map((e) => entryRow(e, edit)).join("")}</div>`;
/* the add-an-entry rows the Feature, Case and Query buttons open: a feature picker, a case key, a query */
const adder = (d) => `<div class="row" data-adder="feature" hidden style="margin-top:12px;gap:8px">${dd({ value: "", options: (d.features || []).map((f) => ({ v: f.id, label: f.path, icon: I.folder })), w: "min(100%, 360px)", label: "Feature", name: "addf", placeholder: "Pick a feature" })}<button class="btn sm" data-add-kind="feature">Add</button></div>
  <div class="row" data-adder="case" hidden style="margin-top:12px;gap:8px"><input id="addc" class="in mono" aria-label="Case key" placeholder="${esc(prodOf(d).key)}-101"><button class="btn sm" data-add-kind="case">Add</button></div>
  <div class="row" data-adder="query" hidden style="margin-top:12px;gap:8px"><input id="addq" class="in" aria-label="Query" placeholder="tags: visa AND priority: high"><button class="btn sm" data-add-kind="query">Add</button></div>`;
/* plan → resolve → pin → cycle; cur is the step in progress, past the last step every step is done */
const flow = (d, cur) => {
  const p = d.detail, r = p.resolve, c = p.cycles[0];
  const S4 = [["Plan", `${esc(p.name)}, ${p.entries.length} entries, scoped to ${esc(p.version)}`],
    ["Resolve", `${r.features} features → ${r.featureCases} cases; query adds ${r.queryNew} new; ${r.cases} case${r.cases === 1 ? "" : "s"}`],
    ["Pin", `${r.pinned} cases pinned at their current version${r.example ? ` (e.g. ${esc(r.example.key)} v${r.example.ver})` : ""}`],
    ["Cycle", c ? `${esc(c.name)}, ${esc(c.status)}` : "no cycle yet"]];
  return `<div class="flow"${cur >= S4.length ? " data-done" : ""}>${S4.map((s, i) => `<div class="fs ${i < cur ? "done" : i === cur ? "cur" : ""}"><span class="no">${i < cur ? "✓" : i + 1}</span><h4>${s[0]}</h4><p>${s[1]}</p></div>`).join("")}</div>`;
};

function detail(d, banner = "", step = 0) {
  const p = d.detail, name = esc(p.name), v = esc(p.version);
  const L = (h, inner, cls = "") => `<a class="fx ${cls}" href="${h}">${inner}</a>`;
  const relHref = p.releaseId ? href("releases", { ...at(d), id: p.releaseId }) : "";
  return head(name, `Test plan · ${esc(prodOf(d).key)} ${v}`, crumbs([[prodLabel(d), prodHref(d)], ...(relHref ? [[v, relHref]] : []), ["Test plans", href("plans", at(d))], [name]]),
    `<a class="btn" href="#edit">${I.edit}Edit entries</a><a class="btn hide-n" href="#create-cycle">${I.cycle}Create cycle only</a><a class="btn primary" href="${href("start", { ...at(d), plan: p.id }, "mode")}">${I.play}Run this plan</a>`) + banner +
  `<div class="card" style="margin-bottom:20px"><div class="hd"><h2>How this plan becomes a cycle</h2></div><div class="bd">${flow(d, step)}</div></div>
  <div class="g2">
    <div class="card"><div class="hd"><h2>What it tests</h2><span class="r">${pillOf(p.status)}<span class="faint" style="font-size:12px;margin-left:8px">${p.entries.length} entries</span></span></div><div class="bd">${entries(d, false)}</div></div>
    <div class="stack">
      <div class="card"><div class="hd"><h2>Scope</h2></div><div class="bd"><div class="fx-r">
        ${L(prodHref(d), `${I.build}<b>${prodLabel(d)}</b>`, "col")}${relHref ? L(relHref, `${I.tag}<b>${v}</b><span class="r"><span class="pill ${p.versionStatus}">${p.versionStatus}</span></span>`, "col") : ""}
      </div></div></div>
      <div class="card"><div class="hd"><h2>Cycles made from this plan</h2></div><div class="bd"><div class="fx-r">
        ${p.cycles.map((c) => L(href("cycles", { ...at(d), id: c.id }), `${I.cycle}<b>${esc(c.name)}</b><span class="r"><span class="pill ${c.status}">${c.status}</span><span class="faint hide-n">${c.pinned} pinned</span></span>`, "col")).join("\n        ")}
      </div>${p.latest ? `<div style="margin-top:14px">${bar(p.latest.results, "", `Latest cycle · ${esc(p.latest.env)}`)}</div>` : ""}</div></div>
    </div>
  </div>`;
}

const newPlan = (d) => {
  const f = d.draft;
  const cur = f.versions.find((v) => v.id === f.version);
  const vers = f.versions.map((v) => ({ v: v.id, label: v.ver, hint: v.status + (v.features ? ` · ${v.features} features` : ""), icon: I.tag }));
  return modal("New test plan", `
  <div class="field"><label for="pn">Name</label><input id="pn" class="in" value="${esc(f.name)}"></div>
  <div class="grid2"><div class="field"><label>Product</label>${dd({ value: f.product, options: d.ctx.products.map((p) => ({ v: p.key, label: `${p.key} · ${p.name}`, icon: mark(p) })), w: "100%", label: "Product", name: "nprod" })}</div>
  <div class="field"><label>Version</label>${dd({ value: f.version, options: [{ v: "none", label: "Any version", hint: "a reusable plan, e.g. smoke" }, "-", { group: `${f.product} versions` }, ...vers], w: "100%", label: "Version", name: "nver", open: true })}</div></div>
  <div class="field"><label>Add tests by</label><div class="seg" role="group" aria-label="Add tests by"><button class="on" aria-pressed="true" data-seg="feature">${I.folder} Feature</button><button aria-pressed="false" data-seg="case">${I.doc} Case</button><button aria-pressed="false" data-seg="query">${I.filter} Query</button></div></div>
  <div data-all${cur ? "" : " hidden"}>${tg(f.allFeatures, `Start with every feature in ${esc(cur ? cur.ver : "")}`, `Adds the ${f.featureCount} features from the version’s release_feature list`, { name: "all" })}</div>
  ${adder(d)}
  <div style="margin-top:14px">${entries(d, true)}</div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="create">Create plan</button>`, "wide");
};

const createCycle = (d) => {
  const p = d.detail, c = d.newCycle;
  const envs = [...c.environments.map((e) => ({ v: e, label: e, icon: I.server })), "-", { v: "new", label: "New environment…", icon: I.plus }];
  const skip = c.deprecated === null ? "Deprecated cases are always left out" : `${c.deprecated} deprecated cases match; they're left out by default`;
  return modal(`Create a cycle from ${esc(p.name)}`, `
  <div style="margin-bottom:18px">${flow(d, 2)}</div>
  <div class="grid2"><div class="field"><label>Environment</label>${dd({ value: c.env, options: envs, w: "100%", label: "Environment", name: "env" })}<input id="cenv" class="in" aria-label="New environment"${c.env === "new" ? "" : " hidden"}></div>
  <div class="field"><label for="cn">Cycle name</label><input id="cn" class="in" value="${esc(c.name)}"></div></div>
  <div class="card" style="box-shadow:none"><div class="bd"><span class="kind" style="display:block;margin-bottom:10px">Resolved now</span><div class="res">
    ${c.resolved.map((r) => `<span>${esc(r.label)}</span><b>${r.count}${r.unit ? " " + esc(r.unit) : ""}</b>`).join("")}<span class="tot">Cases pinned at their current version</span><b class="tot">${p.resolve.pinned}</b>
  </div></div></div>
  <div style="margin-top:14px">${tg(c.skipDeprecated, "Skip deprecated cases", skip, { disabled: true })}</div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="create-cycle">Create cycle with ${p.resolve.pinned} cases</button>`, "wide");
};

const edit = (d) => modal("Edit entries", `<p class="muted" style="margin-top:0">Changes apply to new cycles. Cycles already made keep their pinned cases.</p>${entries(d, true)}<div class="row" style="margin-top:12px;gap:8px"><button class="btn sm" data-seg="feature">${I.folder}Add feature</button><button class="btn sm" data-seg="case">${I.doc}Add case</button><button class="btn sm" data-seg="query">${I.filter}Add query</button></div>${adder(d)}`, `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="save-entries">Save entries</button>`, "wide");

const created = (d) => {
  const p = d.detail, r = p.resolve, c = p.cycles[0];
  const pin = r.example ? ` (${esc(r.example.key)} at ${ver(r.example.ver, 1)})` : "";
  return detail(d, `<div class="banner info" style="margin-bottom:16px">${I.check}<div style="flex:1"><b>Cycle created: ${esc(c.name)}.</b> ${c.pinned} cases pinned${pin}. <a href="${href("cycles", { ...at(d), id: c.id })}">Open cycle</a> · <a href="${href("run", { ...at(d), id: c.id })}">Start running</a></div></div>`, 4);
};

const empty = (d) => listHead(d) + `<div class="card"><div class="empty"><div class="ill">${I.flag}</div><h3>No test plans for ${esc(d.ctx.product.key)}</h3><p class="muted" style="margin:0 auto 14px;max-width:460px">A plan picks features, cases or a query for a version. Create cycles from it as often as you need; each one pins the cases at their versions then.</p><a class="btn primary" href="#new">${I.plus}New plan</a></div></div>`;

/* the real controls: search and filters ask the server, the forms write through data/plans.js */
const picked = (main, name) => { const o = main.querySelector(`[data-name="${name}"] .dd-o.sel`); return o ? o.dataset.v : ""; };
const pickedAll = (main, name) => [...main.querySelectorAll(`[data-name="${name}"] .dd-o.sel`)].map((o) => o.dataset.v);
const failed = (main, btn, label) => (e) => { showError(main.querySelector(".modal .mb"), e, label); btn.disabled = false; };

/* the entry editor in a dialog: Remove marks a saved entry, the adders append new ones; edits() reads both */
function entryEditor(main) {
  const box = main.querySelector(".modal [data-entries]");
  if (!box) return null;
  const removed = [];
  box.addEventListener("click", (e) => {
    const x = e.target.closest("[data-remove]");
    if (!x) return;
    const row = x.closest(".src");
    if (row.dataset.id) removed.push(row.dataset.id);
    row.remove();
  });
  main.querySelectorAll(".modal [data-seg]").forEach((b) => b.addEventListener("click", () => {
    main.querySelectorAll(".modal .seg [data-seg]").forEach((s) => { s.classList.toggle("on", s === b); s.setAttribute("aria-pressed", String(s === b)); });
    main.querySelectorAll(".modal [data-adder]").forEach((r) => { r.hidden = r.dataset.adder !== b.dataset.seg; });
  }));
  const append = (kind, label, add) => box.insertAdjacentHTML("beforeend", entryRow({ kind, label, meta: "new entry, counted when saved", add }, true));
  main.querySelectorAll(".modal [data-add-kind]").forEach((b) => b.addEventListener("click", () => {
    const kind = b.dataset.addKind;
    if (kind === "feature") {
      const o = main.querySelector('[data-name="addf"] .dd-o.sel');
      if (o) append("feature", o.dataset.label, { feature_id: o.dataset.v });
    } else {
      const input = main.querySelector(kind === "case" ? "#addc" : "#addq");
      const text = input.value.trim();
      if (!text) return;
      append(kind, text, kind === "case" ? { case_id: text } : { query: parseQuery(text) });
      input.value = "";
    }
  }));
  return () => ({ remove: removed, add: [...box.querySelectorAll("[data-add]")].map((r) => JSON.parse(r.dataset.add)) });
}

function after(main, state, d) {
  const box = main.querySelector(".psearch input");
  if (box) box.addEventListener("keydown", (e) => {
    if (e.key === "Enter") location.href = href("plans", { q: box.value.trim() || null, version: d.versionFilter === "all" ? null : d.versionFilter, status: d.statusFilter.join(",") });
  });
  const filt = main.querySelector(".row.wrap");
  if (filt && d.statusFilter) filt.addEventListener("dd:change", () => {
    const v = picked(main, "fver");
    location.href = href("plans", { q: d.q || null, version: v === "all" ? null : v, status: pickedAll(main, "fstatus").join(",") || null });
  });
  const edits = entryEditor(main);
  const create = main.querySelector("[data-act=create]");
  if (create) {
    const m = main.querySelector(".modal");
    m.addEventListener("dd:change", (e) => {
      if (e.detail.name === "nprod") location.href = href("plans", { product: e.detail.value }, "new");
      if (e.detail.name !== "nver") return;
      const v = d.draft.versions.find((x) => x.id === e.detail.value);
      const all = m.querySelector("[data-all]");
      all.hidden = !v;
      if (v) all.querySelector(".tg-t").firstChild.textContent = `Start with every feature in ${v.ver}`;
      if (v) all.querySelector(".tg-t small").textContent = `Adds the ${v.features} features from the version’s release_feature list`;
    });
    create.addEventListener("click", async () => {
      create.disabled = true;
      const version = picked(main, "nver");
      const form = { name: main.querySelector("#pn").value.trim(), version, allFeatures: !m.querySelector("[data-all]").hidden && m.querySelector('input[name="all"]').checked, entries: edits().add };
      try {
        const p = await actions.create(form, d.ctx, d.draft.product);
        location.assign(href("plans", { product: d.draft.product, id: p.id }));
      } catch (e) { failed(main, create, "Couldn't create the plan.")(e); }
    });
  }
  const save = main.querySelector("[data-act=save-entries]");
  if (save) save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await actions.saveEntries(d.detail.id, edits(), d.ctx);
      location.assign(href("plans", { ...at(d), id: d.detail.id }));
    } catch (e) { failed(main, save, "Couldn't save the entries.")(e); }
  });
  const cyc = main.querySelector("[data-act=create-cycle]");
  if (cyc) {
    const envIn = main.querySelector("#cenv");
    main.querySelector('[data-name="env"]').addEventListener("dd:change", (e) => { envIn.hidden = e.detail.value !== "new"; });
    cyc.addEventListener("click", async () => {
      cyc.disabled = true;
      const env = picked(main, "env");
      try {
        const c = await actions.createCycle(d.detail.id, { name: main.querySelector("#cn").value.trim(), environment: env === "new" ? envIn.value.trim() : env }, d.ctx, prodOf(d).key);
        location.assign(href("plans", { ...at(d), id: d.detail.id, cycle: c.id }));
      } catch (e) { failed(main, cyc, "Couldn't create the cycle.")(e); }
    });
  }
}

export default { nav: "plans", default: "list", after, states: {
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
