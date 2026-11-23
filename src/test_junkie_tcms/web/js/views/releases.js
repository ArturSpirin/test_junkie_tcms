/* Versions (releases): one product's version list, a version's detail, its feature list and the new-version form.
   The data and the writes are data/releases.js. */
import { I, bar, crumbs, modal, dd, tg, esc } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions } from "../data/releases.js";

const plural = (n, one) => `${n} ${n === 1 ? one : one + "s"}`;
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const prodLabel = (d) => esc(`${d.product.key} · ${d.product.name}`);
const at = (d) => ({ product: d.product.key });
const prodHref = (d) => href("products", { ...at(d), id: d.product.key });
const listHead = (d) => head("Versions", `Catalog · ${prodLabel(d)}`, crumbs([[prodLabel(d), prodHref(d)], ["Versions"]]), `<a class="btn primary" href="#new">${I.plus}New version</a>`);
const meta = (r) => `${esc(r.when)} · ${plural(r.features, "feature")}${r.plans === null ? "" : " · " + plural(r.plans, "plan")} · ${plural(r.cycles, "cycle")}`;
const row = (d, r) => `<a class="vr" href="${href("releases", { ...at(d), id: r.id })}"><div class="v"><b>${esc(r.ver)}</b><span class="pill ${r.status}">${r.status}</span></div>
  <div class="m"><span class="ell">${esc(r.summary)}</span><small>${meta(r)}</small></div>
  ${Object.keys(r.results).length ? bar(r.results, "", esc(d.product.key + " " + r.ver)) : '<span class="faint" style="font-size:12px">no results yet</span>'}<span class="r faint">${I.chev}</span></a>`;
const list = (d) => listHead(d) + `<div class="sub">A version (API: <code>release</code>) lists the features it changes. Test plans target a version, and its cycles pin each case at its current version.</div>
  <div class="card tl" style="gap:0">${d.versions.map((r) => row(d, r)).join('<div style="height:1px;background:var(--edge)"></div>')}</div>`;

function detail(d, banner = "") {
  const v = d.detail;
  const k = v.kpis;
  const ver = esc(v.ver);
  const L = (h, inner, cls = "") => `<a class="fx ${cls}" href="${h}">${inner}</a>`;
  const path = [[I.build, prodLabel(d), prodHref(d)], [I.tag, ver, ""], [I.tree, plural(v.features, "feature"), "#set-features"], [I.flag, plural(v.plans, "test plan"), href("plans", at(d))], [I.cycle, plural(v.cycles, "cycle"), href("cycles", at(d))]];
  return head(esc(`${d.product.key} ${v.ver}`), `Version · ${v.status.replace("_", " ")}`, crumbs([[prodLabel(d), prodHref(d)], ["Versions", href("releases", at(d))], [ver]]),
    `<a class="btn" href="#set-features">${I.tree}Set features</a><a class="btn primary" href="${href("cycles", at(d), "bulk-preview")}">${I.cycle}Create cycles</a>`) + banner +
  `<div class="card" style="margin-bottom:20px"><div class="bd"><div class="path">${path.map((x, i) => `${i ? `<span class="pa">${I.chev}</span>` : ""}${x[2] ? `<a class="pn" href="${x[2]}">${x[0]}${x[1]}</a>` : `<span class="pn on">${x[0]}${x[1]}</span>`}`).join("")}</div></div></div>
  <div class="kpis"><div class="kpi"><div class="l">Status</div><div class="v" style="font-size:18px;padding:5px 0"><span class="pill ${v.status}">${v.status}</span></div><div class="d">target ${esc(v.target)}</div></div><div class="kpi"><div class="l">Cases in scope</div><div class="v">${k.inScope}</div><div class="d">from ${k.fromFeatures} features</div></div><div class="kpi"><div class="l">Executed</div><div class="v">${k.executedPct}%</div><div class="d">${k.executed} of ${k.cycleCases} cycle cases</div></div><div class="kpi"><div class="l">Pass rate</div><div class="v">${k.passPct}%</div><div class="d">success of executed</div></div></div>
  <div class="split">
    <div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">release_feature</span><span>Features in this version</span></div><a class="r btn ghost sm" href="#set-features">Edit</a></div><div class="bd"><div class="fx-r">
      ${v.tree.filter((f) => f.inVersion).map((f) => L(href("tree", at(d)), `${I.folder}<b>${esc(f.path)}</b><span class="faint">${f.cases} cases</span>`, "col")).join("")}
    </div></div></div>
    <div class="stack">
      <div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Planning</span><span>Test plans for ${ver}</span></div><a class="r btn ghost sm" href="${href("plans", at(d), "new")}">${I.plus}New plan</a></div><div class="bd"><div class="fx-r">
        ${v.testPlans.map((p) => L(href("plans", { ...at(d), id: p.id }), `${I.flag}<b>${esc(p.name)}</b><span class="r"><span class="pill ${p.status}">${p.status}</span><span class="faint hide-n">${esc(p.scope)}</span></span>`, "col")).join("\n        ")}
      </div></div></div>
      <div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Execution</span><span>Cycles for ${ver}</span></div></div><div class="bd"><div class="fx-r">
        ${v.cycleList.map((c) => L(href("cycles", { ...at(d), id: c.id }), `${I.cycle}<b>${esc(c.name)}</b><span class="r"><span class="pill ${c.status}">${c.status}</span></span>`, "col")).join("\n        ")}
      </div></div></div>
    </div>
  </div>`;
}

const picked = (d) => d.detail.tree.filter((f) => f.inVersion).length;
const setFeatures = (d) => modal(`Features in ${esc(d.detail.ver)}`, `<p style="margin-top:0" class="muted">Pick the features this version changes. A bulk cycle makes one cycle per picked feature; a plan that picks “all features in the version” resolves from this list when its cycle starts.</p>
  <div class="fpick">${d.detail.tree.map((f) => `<div class="src${f.inVersion ? " on" : ""}${f.sub ? " sub" : ""}" data-id="${esc(f.id)}"><span class="ic">${I.folder}</span><div style="min-width:0"><div class="t1">${esc(f.path)}</div><div class="t2">${f.cases} cases</div></div><span class="r">${tg(f.inVersion, "", "", { name: "f" })}</span></div>`).join("")}</div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="save-features">Save ${picked(d)} features</button>`);

const newForm = (d) => {
  const f = d.draft;
  const key = esc(d.product.key);
  const status = [{ v: "planned", label: "planned", icon: I.calendar }, { v: "in_progress", label: "in_progress", icon: I.clock }, { v: "released", label: "released", icon: I.check }, { v: "cancelled", label: "cancelled", icon: I.x }];
  /* dd() escapes option labels and hints itself */
  const targets = [{ group: "Suggested" }, ...f.targets.map((t) => ({ v: t.v, label: t.label, hint: t.hint, icon: I.calendar })), "-", { v: "none", label: "No target date" }];
  const copy = [{ v: "none", label: "None" }, "-", { group: `${d.product.key} versions` },
    ...f.copyable.map((ver) => d.versions.find((r) => r.ver === ver)).filter(Boolean).map((r) => ({ v: r.ver, label: r.ver, hint: `${r.status.replace("_", " ")} · ${r.features} features`, icon: I.tag }))];
  return modal(`New version of ${key}`, `
  <div class="grid2"><div class="field"><label for="vv">Version</label><input id="vv" class="in mono" value="${esc(f.ver)}"></div>
  <div class="field"><label>Status</label>${dd({ value: f.status, options: status, w: "100%", label: "Status", name: "status" })}</div></div>
  <div class="field"><label for="vn">Name</label><input id="vn" class="in" value="${esc(f.name)}"></div>
  <div class="field"><label for="vt">Target date</label>${dd({ value: f.target, options: targets, w: "100%", label: "Target date", name: "target" })}</div>
  <div class="field"><label>Copy features from</label>${dd({ value: f.copyFrom, options: copy, w: "100%", label: "Copy features from", name: "copy" })}</div>
  <div class="field"><label for="vno">Notes</label><textarea id="vno" class="in" rows="2">${esc(f.notes)}</textarea></div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="create">Create version</button>`);
};

const releasedBanner = (d) => `<div class="banner info">${I.info}<div><b>Mark ${esc(d.detail.ver)} released?</b> ${d.detail.untested} cycle cases are still untested in ${d.detail.openCycles} open cycles. Releasing doesn't close them. <a href="${href("cycles", at(d))}">Review cycles</a></div></div>`;
const saved = (d) => `<div class="toast" role="status"><div><b>${esc(d.detail.ver)} now lists ${picked(d)} features.</b> <span class="muted">Open cycles keep their pinned cases; new cycles use the new list.</span></div></div>`;
const empty = (d) => listHead(d) + `<div class="card"><div class="empty"><div class="ill">${I.tag}</div><h3>No versions for ${esc(d.noVersionsFor)} yet</h3><p class="muted" style="margin:0 auto 14px;max-width:440px">Add a version, list the features it changes, then make a test plan for it or create its cycles in one go.</p><a class="btn primary" href="#new">${I.plus}New version</a></div></div>`;

/* the real controls: Save in the feature picker, Create in the new-version form */
const picks = (main, name) => { const o = main.querySelector(`[data-name="${name}"] .dd-o.sel`); return o ? o.dataset.v : ""; };
function after(main, state, d) {
  const save = main.querySelector("[data-act=save-features]");
  if (save) {
    const on = () => [...main.querySelectorAll(".fpick .src")].filter((x) => x.querySelector("input").checked).map((x) => x.dataset.id);
    main.querySelector(".fpick").addEventListener("change", () => { save.textContent = `Save ${on().length} features`; });
    save.addEventListener("click", async () => {
      save.disabled = true;
      try {
        await actions.setFeatures(d.detail.id, on(), d.ctx);
        location.replace("#features-saved");
      } catch (e) {
        showError(main.querySelector(".modal .mb"), e, "Couldn't save the features.");
        save.disabled = false;
      }
    });
  }
  const create = main.querySelector("[data-act=create]");
  if (create) create.addEventListener("click", async () => {
    const val = (id) => main.querySelector("#" + id).value.trim();
    create.disabled = true;
    try {
      const r = await actions.create({ ver: val("vv"), name: val("vn"), status: picks(main, "status"), target: picks(main, "target"), copyFrom: picks(main, "copy"), notes: val("vno") }, d.ctx, d.product.key);
      location.assign(href("releases", { ...at(d), id: r.id }));
    } catch (e) {
      showError(main.querySelector(".modal .mb"), e, "Couldn't create the version.");
      create.disabled = false;
    }
  });
}

export default { nav: "releases", default: "list", after, states: {
  "list": { render: list },
  "detail": { render: (d) => detail(d) },
  "set-features": { render: (d) => detail(d) + setFeatures(d) },
  "features-saved": { render: (d) => detail(d) + saved(d) },
  "new": { render: (d) => list(d) + newForm(d) },
  "released": { render: (d) => detail(d, releasedBanner(d)) },
  "empty": { render: empty }
}};
