/* Cycles: the cycle list, the new-cycle form, the bulk cycle wizard (pick a release, preview) and one cycle's detail.
   The data and the writes are data/cycles.js. */
import { I, st, ver, actor, modal, bar, legend, dd, crumbs, esc, person } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions } from "../data/cycles.js";

const sum = (c) => Object.values(c).reduce((a, b) => a + b, 0);
const plural = (n, one) => `${n} ${n === 1 ? one : one + "s"}`;
const at = (d) => ({ product: d.product.key });
const who = (x) => (x ? actor(x.kind, esc(x.name), { k: false }) : '<span class="faint">unassigned</span>');

/* option sets, built from data */
const relOpt = (r) => r.status === "released"
  ? { v: r.ver, label: `${r.ver} · ${r.name}`, hint: `released ${r.date}`, dot: "var(--pass)", dis: true }
  : { v: r.ver, label: `${r.ver} · ${r.name}`, short: `${r.ver} · ${r.name}`, hint: `due ${r.date} · ${r.features} affected features`, dot: r.status === "in_progress" ? "var(--retest)" : "var(--muted)" };
const releaseOpts = (d) => {
  const by = (s) => d.releases.filter((r) => r.status === s).map(relOpt);
  return [{ group: "In progress" }, ...by("in_progress"), { group: "Planned" }, ...by("planned"), { group: "Released · can't get new cycles" }, ...by("released"),
    "-", { v: "none", label: "No release", hint: "an ad-hoc cycle, not counted in a release report", icon: I.x }];
};
/* environment is a free label: the ones in use, and a new one */
const envOpts = (d) => [...(d.envs.length ? [{ group: "In use" }] : []), ...d.envs.map((e) => ({ v: e.v, label: e.label, hint: e.hint, icon: I.server })),
  "-", { v: "new", label: "New label…", hint: "environment is a free label", icon: I.plus }];
const whoOpts = (d) => [{ group: "People" },
  ...d.assignees.filter((a) => a.kind === "person").map((a) => ({ v: a.v, label: person(a.v)[0], short: a.short, hint: a.open != null ? `${a.role} · ${a.open} open cases` : a.role, icon: I.person })),
  { group: "Agents" },
  ...d.assignees.filter((a) => a.kind === "agent").map((a) => ({ v: a.v, label: a.name, hint: a.note ? `agent · ${a.note}` : "agent", icon: I.agent })),
  "-", { v: "none", label: "Unassigned", icon: I.dotted }];
const featOpts = (d) => d.featureGroups.flatMap((g) => [{ group: g.name },
  ...g.features.map((f) => ({ v: f.v, label: f.label, short: f.label, hint: `${f.cases} cases`, icon: I.folder }))]);
/* the environment field: the label picker, and a box for a new label */
const envField = (d, value, id) => `${dd({ value, options: envOpts(d), cls: "block", label: "Environment", name: "env" })}<input id="${id}" class="in" placeholder="New environment label" aria-label="New environment label" style="margin-top:8px" hidden>`;

/* cycle list; counts use Test Junkie statuses + untested */
function list(d) {
  const open = (c) => href("cycles", { ...at(d), id: c.id });
  const row = (c) => c.kind === "batch" ? `<tr class="grp"><td colspan="7"><span class="row"><span class="eyebrow">Bulk batch</span><b>${esc(c.name)}</b><span class="muted ell">· ${batchMeta(c)}</span></span></td></tr>`
    : `<tr class="${c.status === "closed" ? "dim" : ""}"><td class="${c.inBatch ? "ind" : ""}"><a href="${open(c)}">${esc(c.name)}</a></td><td>${c.release ? `<span class="chip mono">${esc(c.release)}</span>` : '<span class="faint">none</span>'}</td><td>${c.env ? `<span class="chip">${esc(c.env)}</span>` : '<span class="faint">none</span>'}</td>
      <td class="hide-m">${who(c.assignee)}</td><td style="min-width:160px">${bar(c.results)}</td><td class="num">${sum(c.results)}</td><td><span class="pill ${c.status}">${c.status}</span></td></tr>`;
  const mrow = (c) => c.kind === "batch" ? `<div class="it grp"><span class="eyebrow">Bulk batch</span><b>${esc(c.name)}</b><span class="muted" style="font-size:12px">${batchMeta(c)}</span></div>`
    : `<div class="it"><div class="row"><a href="${open(c)}" class="ell" style="flex:1">${esc(c.name)}</a><span class="pill ${c.status}">${c.status}</span></div><div class="row">${c.release ? `<span class="chip mono">${esc(c.release)}</span>` : ""}${c.env ? `<span class="chip">${esc(c.env)}</span>` : ""}<span class="faint" style="font-size:12px">${sum(c.results)} cases</span></div>${bar(c.results)}</div>`;
  return `<div class="card"><div class="tbl-wrap mswap"><table class="t"><thead><tr><th>Cycle</th><th>Release</th><th>Environment</th><th class="hide-m">Default assignee</th><th>Results</th><th class="num">Cases</th><th>Cycle</th></tr></thead><tbody>${d.rows.map(row).join("")}</tbody></table></div><div class="mlist">${d.rows.map(mrow).join("")}</div></div><div style="margin-top:14px">${legend()}</div>`;
}
const batchMeta = (c) => `${c.cycles} cycles, one per ${c.per === "plans" ? "test plan" : "affected feature"} · created ${esc(c.on)}`;
const productCrumb = (d) => [`${esc(d.product.key)} · ${esc(d.product.name)}`, href("products", { ...at(d), id: d.product.key })];
const head = (d) => `${crumbs([productCrumb(d), ["Cycles"]])}
<div class="eyebrow">Execution</div>
<div class="ph" style="margin-top:6px"><h1>Cycles</h1><div class="actions"><a class="btn" href="#bulk-pick-release">${I.cycle}Bulk cycle from a release</a><a class="btn primary" href="#new-cycle">${I.plus}New cycle</a></div></div>`;
const filters = (d) => `<div class="cyc-filters">
  <label class="in-ic">${I.search}<input class="in" placeholder="Filter cycles" aria-label="Filter cycles"></label>
  ${dd({ value: d.filter.release, options: [{ v: "any", label: "Any release" }, "-"].concat(releaseOpts(d).filter((o) => o !== "-" && o.v !== "none").map((o) => (o.dis ? Object.assign({}, o, { dis: false }) : o))), cls: "sm", pre: "Release", label: "Release" })}
  ${dd({ value: d.filter.env, options: [{ v: "any", label: "Any environment" }, "-"].concat(envOpts(d).filter((o) => o.v !== "new" && o !== "-")), cls: "sm", pre: "Env", label: "Environment" })}
  ${dd({ value: d.filter.assignee, options: [{ v: "any", label: "Anyone" }, "-"].concat(whoOpts(d)), cls: "sm hide-n", pre: "Assignee", label: "Assignee" })}
</div>`;
const tabs = (d) => {
  const t = (s, label) => `<a${d.filter.status === s ? ' class="on"' : ""} href="${href("cycles", { ...at(d), status: s === "open" ? null : s })}">${label}</a>`;
  return `<div class="tabs">${t("open", `Open (${d.tabs.open})`)}${t("closed", `Closed (${d.tabs.closed})`)}${t("all", "All")}</div>`;
};
const listPage = (d) => head(d) + tabs(d) + filters(d) + list(d);

const newCycle = (d) => {
  const f = d.draft;
  return modal("New cycle", `
  <div class="eyebrow" style="margin-bottom:10px">Cases</div>
  <div class="field"><label>Add cases from</label><div class="seg"><button>Test plan</button><button class="on acc">Features</button><button>Pick cases</button></div></div>
  <div class="field"><label>Features</label>${dd({ value: f.features, multi: true, search: "Find a feature", options: featOpts(d), cls: "block", label: "Features", name: "features" })}</div>
  <div class="divider"></div>
  <div class="eyebrow" style="margin-bottom:10px">Cycle</div>
  <div class="grid2"><div class="field"><label for="n">Name</label><input id="n" class="in" value="${esc(f.name)}"></div>
  <div class="field"><label>Release <span class="muted">optional</span></label>${dd({ value: f.release, options: releaseOpts(d), cls: "block", label: "Release", name: "release" })}</div></div>
  <div class="grid2"><div class="field"><label>Environment</label>${envField(d, f.env, "envnew")}<span class="hint">A free label: staging, prod-eu, iPhone 15 / iOS 18</span></div>
  <div class="field"><label>Default assignee</label>${dd({ value: f.assignee, options: whoOpts(d), cls: "block up", label: "Default assignee", name: "assignee" })}</div></div>
  <div class="banner info mb0" id="pv">${pinned(f)}</div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="create">Create cycle</button>`, "wide");
};
/* what the server says the cycle would pin */
const pinned = (f) => {
  const out = [f.deprecated ? `${f.deprecated} deprecated` : "", f.archived ? `${f.archived} archived` : ""].filter(Boolean).join(", ");
  return `${I.pin}<div><b>${plural(f.total, "case")}</b>${out ? ` (${out} left out)` : ""}. Each is pinned at its <b>current version</b> now. Later edits don't change this cycle.</div>`;
};

const bulkRelease = (d) => d.releases.find((r) => r.ver === d.bulk.release);
const bulkPick = (d) => {
  const r = bulkRelease(d);
  return modal("Bulk cycle · 1 of 2 · pick a release", `
  <p class="muted" style="margin-top:0">A bulk cycle starts from a release: one cycle per affected feature of the release, or one per test plan you pick.</p>
  <div class="field mb0"><label>Release</label>${dd({ value: r.ver, options: releaseOpts(d).filter((o) => o.v !== "none" && o !== "-"), search: "Find a release", open: true, cls: "block inl", label: "Release", name: "bulk-release" })}</div>
  <div class="sel-card" style="margin-top:16px"><span class="ic">${I.flag}</span><b><span class="mono">${esc(r.ver)}</span> ${esc(r.name)}</b><span class="pill ${r.status}">${r.status}</span><span class="muted" style="font-size:12.5px;grid-column:2 / -1">Target ${esc(r.date)} · ${r.features} affected features · ${d.bulk.cases} cases</span></div>
  <div class="faint" style="font-size:12px;margin-top:10px">Released and cancelled releases can't get new cycles.</div>`,
  `<button class="btn" data-back>Cancel</button><a class="btn primary" href="#bulk-preview">Next${I.chev}</a>`, "wide");
};

const bulkTotals = (d) => ({ cycles: d.bulk.features.length, cases: d.bulk.total });
const bulkPreview = (d) => {
  const b = d.bulk, r = bulkRelease(d), n = bulkTotals(d);
  const per = (p, label) => `<button${b.per === p ? ' class="on acc"' : ""} data-go="${href("cycles", { ...at(d), release: b.releaseId, per: p === "plans" ? p : null }, "bulk-preview")}">${label}</button>`;
  const cases = (f) => (f.cases === null ? '<span class="faint">–</span>' : f.cases);
  return modal(`Bulk cycle · 2 of 2 · ${esc(r.ver)} ${esc(r.name)}`, `
  <div class="field"><label>One cycle per</label><div class="seg">${per("features", `Affected feature (${b.featureCount})`)}${per("plans", `Test plan (${b.plans})`)}</div></div>
  <div class="field"><label>Environment</label>${envField(d, b.env, "bulkenv")}</div>
  <div class="card"><div class="hd"><span class="eyebrow">Preview</span><span class="r faint" style="font-size:12px">${n.cycles} cycles · ${n.cases} cases</span></div><div class="tbl-wrap mswap"><table class="t"><thead><tr><th>Cycle</th><th class="num">Cases</th></tr></thead><tbody>
  ${b.features.map((f) => `<tr><td><span class="ell" style="display:block;max-width:300px">${esc(f.path)}</span></td><td class="num">${cases(f)}</td></tr>`).join("")}
  </tbody></table></div>
  <div class="mlist">${b.features.map((f) => `<div class="it"><span class="ell">${esc(f.path)}</span>${f.cases === null ? "" : `<span class="muted" style="font-size:12px">${f.cases} cases</span>`}</div>`).join("")}</div></div>
  <div class="banner info mb0" style="margin-top:16px">${I.pin}<div>${n.cases} cases, each <b>pinned at its current version</b>. Grouped as one bulk batch so the release report adds them up.</div></div>`,
  `<a class="btn" href="#bulk-pick-release">${I.chevl}Back</a><button class="btn primary" data-act="bulk"${n.cycles ? "" : " disabled"}>Create ${n.cycles} cycles</button>`, "wide");
};
const bulkCreated = (d) => {
  const n = bulkTotals(d);
  return `<div class="toast" role="status"><div><b>${n.cycles} cycles created for ${esc(d.bulk.release)}.</b> <span class="muted">${n.cases} cases pinned at current versions.</span></div></div>`;
};

function detail(d, banner = "") {
  const c = d.cycle;
  const closed = c.status === "closed";
  const k = c.counts;
  const n = (s) => k[s] || 0;
  const here = { ...at(d), id: c.id };
  const refreshCell = (x) => {
    if (!x.newer) return '<span class="faint">–</span>';
    return closed ? `<button class="btn sm" disabled>${I.restore}Refresh to v${x.newer}</button>` : `<a class="btn sm" href="${href("cycles", { ...here, cc: x.id }, "refresh-confirm")}">${I.restore}Refresh to v${x.newer}</a>`;
  };
  const run = (x) => href("run", { ...at(d), id: c.id, cc: x ? x.id : null });
  const stCell = (x) => `${st(x.status)}${x.note ? `<span class="why">${esc(x.note)}</span>` : ""}`;
  const r = (x) => `<tr><td class="key">${esc(x.key)}</td><td class="tt"><span class="ell" title="${esc(x.title)}">${esc(x.title)}</span></td><td>${ver(x.pinned, 1)}</td><td class="hide-m">${refreshCell(x)}</td><td class="hide-m">${who(x.assignee)}</td><td>${stCell(x)}</td><td class="hide-m">${x.attempt > 1 ? `<span class="chip acc">attempt ${x.attempt}</span>` : x.attempt ? '<span class="faint">1</span>' : '<span class="faint">–</span>'}</td><td>${closed ? "" : `<a class="btn sm ghost" href="${run(x)}">${I.run}Run</a>`}</td></tr>`;
  const m = (x) => `<div class="it"><div class="row"><span class="key">${esc(x.key)}</span>${ver(x.pinned, 1)}${st(x.status)}${x.attempt > 1 ? `<span class="chip acc">attempt ${x.attempt}</span>` : ""}</div><span>${esc(x.title)}</span>${x.note ? `<span class="why" style="margin:0">${esc(x.note)}</span>` : ""}${x.newer && x.hasResult ? `<span class="faint" style="font-size:12px">results kept as history</span>` : ""}${x.newer && !closed ? `<a class="btn sm" style="justify-self:start" href="${href("cycles", { ...here, cc: x.id }, "refresh-confirm")}">${I.restore}Refresh to v${x.newer}</a>` : ""}</div>`;
  const L = (h, inner) => `<a class="fx" href="${h}">${inner}</a>`;
  const relHref = href("releases", { ...at(d), id: c.releaseId });
  const planHref = href("plans", { ...at(d), id: c.planId });
  const ids = [c.planId ? `plan_id ${esc(c.planId)}` : "", c.releaseId ? `release_id ${esc(c.releaseId)}` : "", c.batch ? `batch ${esc(c.batch)}` : ""].filter(Boolean).join(" · ");
  const from = `<div class="card" style="margin-bottom:20px"><div class="hd"><div class="ttl"><span class="eyebrow">Made from</span><span>Plan, version and features</span></div><span class="r faint hide-n" style="font-size:12px">${ids}</span></div><div class="bd">
    <div class="path" style="margin-bottom:14px"><a class="pn" href="${productCrumb(d)[1]}">${I.build}${esc(d.product.key)}</a>${c.release ? `<span class="pa">${I.chev}</span><a class="pn" href="${relHref}">${I.tag}${esc(c.release)}</a>` : ""}${c.plan ? `<span class="pa">${I.chev}</span><a class="pn" href="${planHref}">${I.flag}${esc(c.plan)}</a>` : ""}<span class="pa">${I.chev}</span><span class="pn on">${I.cycle}This cycle</span></div>
    <div class="fx-r">${c.features.map((f) => L(href("tree", at(d)), `${I.folder}<b>${esc(f.path)}</b><span class="faint">${f.cases} cases</span>`)).join("")}</div>
  </div></div>`;
  const trail = [productCrumb(d), ...(c.release ? [[esc(c.release), relHref]] : []), ...(c.plan ? [[esc(c.plan), planHref]] : []), ["Cycles", href("cycles", at(d))], [esc(c.name)]];
  return `${crumbs(trail)}
  <div class="eyebrow">Cycle · ${esc(c.id)}</div>
  <div class="ph" style="margin-top:6px"><h1>${esc(c.name)}</h1><span class="pill ${closed ? "closed" : "open"}">${closed ? "closed" : "open"}</span>${c.release ? `<span class="chip mono">${esc(c.release)}</span>` : ""}${c.env ? `<span class="chip">${esc(c.env)}</span>` : ""}
  <div class="actions">${closed ? `<button class="btn" data-act="reopen">Reopen</button>` : `<button class="btn">${I.plus}Add cases</button><button class="btn" data-act="close">${I.lock}Close cycle</button><a class="btn primary" href="${run()}">${I.run}Run next untested</a>`}</div></div>
  ${closed ? `<div class="banner">${I.lock}<div>Closed ${esc(c.closedAt)}. Results are read only; reopening is audited.</div></div>` : ""}${banner}
  <div class="kpis">
    <div class="kpi"><div class="l">Cases</div><div class="v">${sum(k)}</div><div class="d">${bar(k)}</div></div>
    <div class="kpi"><div class="l">Success</div><div class="v">${n("success")}</div><div class="d">${st("success")}</div></div>
    <div class="kpi"><div class="l">Fail · error</div><div class="v">${n("fail")} · ${n("error")}</div><div class="d">${n("skip")} skip · ${n("ignore")} ignore</div></div>
    <div class="kpi"><div class="l">No result yet</div><div class="v">${n("untested")}</div><div class="d">${st("untested")}</div></div></div>
  ${from}
  <div class="card"><div class="hd">Cases<span class="r faint" style="font-size:12px">${ver("", 1).replace(">v<", "><")} = case_version pinned when added</span></div>
  <div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Key</th><th>Title</th><th>Pinned</th><th class="hide-m">Newer version</th><th class="hide-m">Assignee</th><th>Status</th><th class="hide-m">Attempt</th><th></th></tr></thead><tbody>${c.cases.map(r).join("")}</tbody></table></div>
  <div class="mlist">${c.cases.map(m).join("")}</div></div>
  <div style="margin-top:14px">${legend(k)}</div>`;
}

const refreshConfirm = (d) => {
  const f = d.refresh;
  const lines = [f.step ? `Step ${esc(f.step)} expected: <del>${esc(f.before)}</del> <ins>${esc(f.after)}</ins>` : "", f.tagsAdded.length ? `Tags: <ins>${esc(f.tagsAdded.join(", "))}</ins>` : ""].filter(Boolean);
  const body = f.results
    ? `This case runs v${f.to} from now on and goes back to untested. ${f.results === 1 ? "Its result stays" : `Its ${f.results} results stay`} in its history, each with the version it ran.`
    : `This case runs v${f.to} from now on.`;
  return modal(`Refresh to v${f.to}?`, `<p style="margin-top:0">${body}</p>
    ${lines.length ? `<div class="diff card"><div class="bd" style="font-size:13px">${lines.join("<br>")}</div></div>` : ""}
    <p class="muted" style="font-size:13px">The refresh is recorded in the audit log as <code>cycle_case.refresh_version</code>.</p>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="refresh">Refresh</button>`);
};
const refused = (d) => `<div class="banner err">${I.warn}<div style="flex:1;min-width:0"><b>Not refreshed.</b> The server said:
<pre class="raw">${esc(d.error)}</pre></div></div>`;

const empty = (d) => head(d) + `<div class="card"><div class="empty"><div class="ill">${I.cycle}</div><h3>No cycles yet</h3><div>A cycle pins the current version of each case so results stay comparable.<br>Start from a release to get one cycle per affected feature.</div>
    <a class="btn primary" href="#bulk-pick-release">Bulk cycle from a release</a> <a class="btn" href="#new-cycle">New cycle</a></div></div>`;

/* the real controls: create, bulk create, close, reopen and refresh; each shows a failure raw */
const pick = (main, name) => { const o = main.querySelector(`[data-name="${name}"] .dd-o.sel`); return o ? o.dataset.v : ""; };
const picks = (main, name) => [...main.querySelectorAll(`[data-name="${name}"] .dd-o.sel`)].map((o) => o.dataset.v);
const relId = (d, v) => { const r = d.releases.find((x) => x.ver === v); return r ? r.id : null; };
/* the environment picked, or the new label typed */
const envOf = (main, box) => { const v = pick(main, "env"); return v === "new" ? main.querySelector("#" + box).value.trim() : v; };
function act(main, sel, label, run, where) {
  const b = main.querySelector(`[data-act=${sel}]`);
  if (!b) return;
  b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      await run();
    } catch (e) {
      showError(where(), e, label);
      b.disabled = false;
    }
  });
}
function after(main, id, d) {
  const dlg = () => main.querySelector(".modal .mb");
  main.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => location.assign(b.dataset.go)));
  const modalEl = main.querySelector(".modal");
  if (modalEl) modalEl.addEventListener("dd:change", async (e) => {
    const { name, value } = e.detail;
    if (name === "env") main.querySelectorAll("#envnew, #bulkenv").forEach((x) => { x.hidden = value !== "new"; });
    if (name === "bulk-release") location.assign(href("cycles", { ...at(d), release: relId(d, value) }, "bulk-pick-release"));
    if (name === "features") {
      try {
        const p = await actions.preview(picks(main, "features"), d.ctx, d.product.key);
        main.querySelector("#pv").innerHTML = pinned({ total: p.total, deprecated: p.skipped.deprecated || 0, archived: p.skipped.archived || 0 });
      } catch (err) {
        showError(dlg(), err, "Couldn't count the cases.");
      }
    }
  });
  act(main, "create", "Couldn't create the cycle.", async () => {
    const release = pick(main, "release");
    const assignee = pick(main, "assignee");
    const c = await actions.create({
      name: main.querySelector("#n").value.trim(), featureIds: picks(main, "features"),
      releaseId: release && release !== "none" ? relId(d, release) : null, environment: envOf(main, "envnew") || null,
      assigneeId: assignee && assignee !== "none" ? assignee : null
    }, d.ctx, d.product.key);
    location.assign(href("cycles", { ...at(d), id: c.id }));
  }, dlg);
  act(main, "bulk", "Couldn't create the cycles.", async () => {
    const b = await actions.bulk(d.bulk.releaseId, { per: d.bulk.per, environment: envOf(main, "bulkenv") || null }, d.ctx);
    location.assign(href("cycles", { ...at(d), batch: b.id }, "bulk-created"));
  }, dlg);
  const page = () => main;
  const reload = () => location.assign(href("cycles", { ...at(d), id: d.cycle.id }));
  act(main, "close", "Couldn't close the cycle.", async () => { await actions.close(d.cycle.id, d.ctx); reload(); }, page);
  act(main, "reopen", "Couldn't reopen the cycle.", async () => { await actions.reopen(d.cycle.id, d.ctx); reload(); }, page);
  act(main, "refresh", "Not refreshed.", async () => { await actions.refresh(d.refresh.id, d.ctx); reload(); }, dlg);
}

export default { nav: "cycles", default: "list", after,
  states: {
    "list": { render: listPage },
    "new-cycle": { render: (d) => listPage(d) + newCycle(d) },
    "bulk-pick-release": { render: (d) => listPage(d) + bulkPick(d) },
    "bulk-preview": { render: (d) => listPage(d) + bulkPreview(d) },
    "bulk-created": { render: (d) => listPage(d) + bulkCreated(d) },
    "detail": { render: (d) => detail(d) },
    "refresh-confirm": { render: (d) => detail(d) + refreshConfirm(d) },
    "refresh-409": { render: (d) => detail(d, refused(d)) },
    "closed": { render: (d) => detail(d) },
    "empty": { render: empty }
  }
};
