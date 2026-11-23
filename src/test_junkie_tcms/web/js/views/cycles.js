/* Cycles: the cycle list, the new-cycle form, the bulk cycle wizard (pick a release, preview) and one cycle's detail. */
import { I, st, ver, actor, modal, bar, legend, dd, tg, toast, crumbs, lnk, esc, person } from "../ui.js";

const sum = (c) => Object.values(c).reduce((a, b) => a + b, 0);

/* option sets, built from data */
const relOpt = (r) => r.status === "released"
  ? { v: r.ver, label: `${r.ver} · ${r.name}`, hint: `released ${r.date}`, dot: "var(--pass)", dis: true }
  : { v: r.ver, label: `${r.ver} · ${r.name}`, short: `${r.ver} · ${r.name}`, hint: `due ${r.date} · ${r.features} affected features`, dot: r.status === "in_progress" ? "var(--retest)" : "var(--muted)" };
const releaseOpts = (d) => {
  const by = (s) => d.releases.filter((r) => r.status === s).map(relOpt);
  return [{ group: "In progress" }, ...by("in_progress"), { group: "Planned" }, ...by("planned"), { group: "Released · can't get new cycles" }, ...by("released"),
    "-", { v: "none", label: "No release", hint: "an ad-hoc cycle, not counted in a release report", icon: I.x }];
};
const envOpts = (d) => {
  const by = (k, icon) => d.envs.filter((e) => e.kind === k).map((e) => ({ v: e.v, label: e.label, hint: e.hint, icon }));
  return [{ group: "Web" }, ...by("web", I.server), { group: "Devices" }, ...by("device", I.tag), "-", { v: "new", label: "New label…", hint: "environment is a free label", icon: I.plus }];
};
const whoOpts = (d) => [{ group: "People" },
  ...d.assignees.filter((a) => a.kind === "person").map((a) => ({ v: a.v, label: person(a.v)[0], short: a.short, hint: a.open != null ? `${a.role} · ${a.open} open cases` : a.role, icon: I.person })),
  { group: "Agents" },
  ...d.assignees.filter((a) => a.kind === "agent").map((a) => ({ v: a.v, label: a.name, hint: `agent · ${a.note}`, icon: I.agent })),
  "-", { v: "none", label: "Unassigned", icon: I.dotted }];
const featOpts = (d) => d.featureGroups.flatMap((g) => [{ group: g.name },
  ...g.features.map((f) => ({ v: f.v, label: f.label, short: f.label, hint: `${f.cases} cases${f.drafts ? ` · ${f.drafts} draft` : ""}`, icon: I.folder }))]);

/* cycle list; counts use Test Junkie statuses + untested */
function list(d) {
  const row = (c) => c.kind === "batch" ? `<tr class="grp"><td colspan="7"><span class="row"><span class="eyebrow">Bulk batch</span><b>${esc(c.name)}</b><span class="muted ell">· ${batchMeta(c)}</span></span></td></tr>`
    : `<tr class="${c.status === "closed" ? "dim" : ""}"><td class="${c.inBatch ? "ind" : ""}"><a href="#detail">${esc(c.name)}</a></td><td>${c.release ? `<span class="chip mono">${esc(c.release)}</span>` : '<span class="faint">none</span>'}</td><td><span class="chip">${esc(c.env)}</span></td>
      <td class="hide-m">${actor(c.assignee.kind, esc(c.assignee.name), { k: false })}</td><td style="min-width:160px">${bar(c.results)}</td><td class="num">${sum(c.results)}</td><td><span class="pill ${c.status}">${c.status}</span></td></tr>`;
  const mrow = (c) => c.kind === "batch" ? `<div class="it grp"><span class="eyebrow">Bulk batch</span><b>${esc(c.name)}</b><span class="muted" style="font-size:12px">${batchMeta(c)}</span></div>`
    : `<div class="it"><div class="row"><a href="#detail" class="ell" style="flex:1">${esc(c.name)}</a><span class="pill ${c.status}">${c.status}</span></div><div class="row">${c.release ? `<span class="chip mono">${esc(c.release)}</span>` : ""}<span class="chip">${esc(c.env)}</span><span class="faint" style="font-size:12px">${sum(c.results)} cases</span></div>${bar(c.results)}</div>`;
  return `<div class="card"><div class="tbl-wrap mswap"><table class="t"><thead><tr><th>Cycle</th><th>Release</th><th>Environment</th><th class="hide-m">Default assignee</th><th>Results</th><th class="num">Cases</th><th>Cycle</th></tr></thead><tbody>${d.rows.map(row).join("")}</tbody></table></div><div class="mlist">${d.rows.map(mrow).join("")}</div></div><div style="margin-top:14px">${legend()}</div>`;
}
const batchMeta = (c) => `${c.cycles} cycles, one per affected feature · created by ${esc(person(c.by)[0])}, ${esc(c.on)}`;
const productCrumb = (d) => [`${esc(d.ctx.product.key)} · ${esc(d.ctx.product.name)}`, "products.html#detail"];
const head = (d) => `${crumbs([productCrumb(d), ["Cycles"]])}
<div class="eyebrow">Execution</div>
<div class="ph" style="margin-top:6px"><h1>Cycles</h1><div class="actions"><button class="btn" data-hash="bulk-pick-release">${I.cycle}Bulk cycle from a release</button><button class="btn primary" data-hash="new-cycle">${I.plus}New cycle</button></div></div>`;
const filters = (d) => `<div class="cyc-filters">
  <label class="in-ic">${I.search}<input class="in" placeholder="Filter cycles" aria-label="Filter cycles"></label>
  ${dd({ value: d.filter.release, options: [{ v: "any", label: "Any release" }, "-"].concat(releaseOpts(d).filter((o) => o !== "-" && o.v !== "none").map((o) => (o.dis ? Object.assign({}, o, { dis: false }) : o))), cls: "sm", pre: "Release", label: "Release" })}
  ${dd({ value: d.filter.env, options: [{ v: "any", label: "Any environment" }, "-"].concat(envOpts(d).filter((o) => o.v !== "new" && o !== "-")), cls: "sm", pre: "Env", label: "Environment" })}
  ${dd({ value: d.filter.assignee, options: [{ v: "any", label: "Anyone" }, "-"].concat(whoOpts(d)), cls: "sm hide-n", pre: "Assignee", label: "Assignee" })}
</div>`;
const listPage = (d) => head(d) + `<div class="tabs"><a class="on">Open (${d.tabs.open})</a><a>Closed (${d.tabs.closed})</a><a>All</a></div>` + filters(d) + list(d);

const newCycle = (d) => {
  const f = d.draft;
  return modal("New cycle", `
  <div class="eyebrow" style="margin-bottom:10px">Cases</div>
  <div class="field"><label>Add cases from</label><div class="seg"><button>Test plan</button><button class="on acc">Features</button><button>Pick cases</button></div></div>
  <div class="field"><label>Features</label>${dd({ value: f.features, multi: true, search: "Find a feature", options: featOpts(d), cls: "block", label: "Features" })}</div>
  <div class="divider"></div>
  <div class="eyebrow" style="margin-bottom:10px">Cycle</div>
  <div class="grid2"><div class="field"><label for="n">Name</label><input id="n" class="in" value="${esc(f.name)}"></div>
  <div class="field"><label>Release <span class="muted">optional</span></label>${dd({ value: f.release, options: releaseOpts(d), cls: "block", label: "Release" })}</div></div>
  <div class="grid2"><div class="field"><label>Environment</label>${dd({ value: f.env, options: envOpts(d), cls: "block", label: "Environment" })}<span class="hint">A free label: staging, prod-eu, iPhone 15 / iOS 18</span></div>
  <div class="field"><label>Default assignee</label>${dd({ value: f.assignee, options: whoOpts(d), cls: "block up", label: "Default assignee" })}</div></div>
  <div class="tg-list" style="margin-bottom:18px">${tg(true, "Skip draft cases", `${f.drafts} drafts in these features stay out of the cycle`)}${tg(false, "Notify the assignee", `Email ${esc(person(f.assignee)[0])} when the cycle opens`)}</div>
  <div class="banner info mb0">${I.pin}<div><b>${f.total} cases</b> (${f.ready} ready, ${f.drafts} draft skipped, ${f.deprecated} deprecated). Each is pinned at its <b>current version</b> now, e.g. ${esc(f.sample.key)} ${ver(f.sample.ver, 1)}. Later edits don't change this cycle.</div></div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-create>Create cycle</button>`, "wide");
};

const bulkRelease = (d) => d.releases.find((r) => r.ver === d.bulk.release);
const bulkPick = (d) => {
  const r = bulkRelease(d);
  return modal("Bulk cycle · 1 of 2 · pick a release", `
  <p class="muted" style="margin-top:0">A bulk cycle starts from a release: one cycle per affected feature of the release, or one per test plan you pick.</p>
  <div class="field mb0"><label>Release</label>${dd({ value: r.ver, options: releaseOpts(d).filter((o) => o.v !== "none" && o !== "-"), search: "Find a release", open: true, cls: "block inl", label: "Release" })}</div>
  <div class="sel-card" style="margin-top:16px"><span class="ic">${I.flag}</span><b><span class="mono">${esc(r.ver)}</span> ${esc(r.name)}</b><span class="pill ${r.status}">${r.status}</span><span class="muted" style="font-size:12.5px;grid-column:2 / -1">Target ${esc(r.date)} · ${r.features} affected features · ${d.bulk.ready} ready cases</span></div>
  <div class="faint" style="font-size:12px;margin-top:10px">Released and cancelled releases can't get new cycles.</div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-hash="bulk-preview">Next${I.chev}</button>`, "wide");
};

const bulkTotals = (d) => ({ cycles: d.bulk.features.length, cases: d.bulk.features.reduce((a, f) => a + f.cases, 0) });
const bulkPreview = (d) => {
  const b = d.bulk, r = bulkRelease(d), n = bulkTotals(d), who = whoOpts(d);
  return modal(`Bulk cycle · 2 of 2 · ${esc(r.ver)} ${esc(r.name)}`, `
  <div class="field"><label>One cycle per</label><div class="seg"><button class="on acc">Affected feature (${n.cycles})</button><button>Test plan</button></div></div>
  <div class="grid2"><div class="field"><label>Environment</label>${dd({ value: b.env, options: envOpts(d), cls: "block", label: "Environment" })}</div><div class="field"><label for="nm">Name pattern</label><input id="nm" class="in mono" value="${esc(b.pattern)}"></div></div>
  <div class="card"><div class="hd"><span class="eyebrow">Preview</span><span class="r faint" style="font-size:12px">${n.cycles} cycles · ${n.cases} cases</span></div><div class="tbl-wrap mswap"><table class="t"><thead><tr><th>Cycle</th><th class="num">Cases</th><th class="hide-n">Skipped</th><th>Assignee</th></tr></thead><tbody>
  ${b.features.map((f) => `<tr><td><span class="ell" style="display:block;max-width:300px">${esc(f.path)}</span></td><td class="num">${f.cases}</td><td class="hide-n faint">${f.drafts ? f.drafts + " draft" : "–"}</td><td>${dd({ value: f.assignee, options: who, cls: "sm", w: "190px", label: "Assignee for " + f.path })}</td></tr>`).join("")}
  </tbody></table></div>
  <div class="mlist">${b.features.map((f) => `<div class="it"><span class="ell">${esc(f.path)}</span><span class="muted" style="font-size:12px">${f.cases} cases${f.drafts ? ` · ${f.drafts} draft skipped` : ""}</span>${dd({ value: f.assignee, options: who, cls: "sm block", label: "Assignee for " + f.path })}</div>`).join("")}</div></div>
  <div class="tg-list" style="margin-top:16px">${tg(true, "Group as one bulk batch", `The release report adds the ${n.cycles} cycles up`)}${tg(true, "Skip draft cases", `${b.drafts} drafts stay out`)}</div>
  <div class="banner info mb0" style="margin-top:16px">${I.pin}<div>${n.cases} cases, each <b>pinned at its current version</b>. Grouped as one bulk batch so the release report adds them up.</div></div>`,
  `<button class="btn" data-hash="bulk-pick-release">${I.chevl}Back</button><button class="btn primary" data-hash="bulk-created">Create ${n.cycles} cycles</button>`, "wide");
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
  const refreshCell = (x) => {
    if (!x.newer) return '<span class="faint">–</span>';
    if (x.hasResult) return `<span class="row" title="Has a result: the pinned version can't change">${ver(x.newer)}<span class="faint" style="font-size:12px">stays pinned</span></span>`;
    return `<button class="btn sm" data-hash="refresh-confirm" ${closed ? "disabled" : ""}>${I.restore}Refresh to v${x.newer}</button>`;
  };
  const stCell = (x) => `${st(x.status)}${x.note ? `<span class="why">${esc(x.note)}</span>` : ""}`;
  const r = (x) => `<tr><td class="key">${esc(x.key)}</td><td class="tt"><span class="ell" title="${esc(x.title)}">${esc(x.title)}</span></td><td>${ver(x.pinned, 1)}</td><td class="hide-m">${refreshCell(x)}</td><td class="hide-m">${actor(x.assignee.kind, esc(x.assignee.name), { k: false })}</td><td>${stCell(x)}</td><td class="hide-m">${x.attempt > 1 ? `<span class="chip acc">attempt ${x.attempt}</span>` : x.attempt ? '<span class="faint">1</span>' : '<span class="faint">–</span>'}</td><td>${closed ? "" : `<a class="btn sm ghost" href="${lnk("run.html")}">${I.run}Run</a>`}</td></tr>`;
  const m = (x) => `<div class="it"><div class="row"><span class="key">${esc(x.key)}</span>${ver(x.pinned, 1)}${st(x.status)}${x.attempt > 1 ? `<span class="chip acc">attempt ${x.attempt}</span>` : ""}</div><span>${esc(x.title)}</span>${x.note ? `<span class="why" style="margin:0">${esc(x.note)}</span>` : ""}${x.newer && !x.hasResult && !closed ? `<button class="btn sm" style="justify-self:start" data-hash="refresh-confirm">${I.restore}Refresh to v${x.newer}</button>` : x.newer ? `<span class="faint" style="font-size:12px">v${x.newer} available · has a result, stays pinned</span>` : ""}</div>`;
  const L = (h, inner) => `<a class="fx" href="${lnk(h)}">${inner}</a>`;
  const from = `<div class="card" style="margin-bottom:20px"><div class="hd"><div class="ttl"><span class="eyebrow">Made from</span><span>Plan, version and features</span></div><span class="r faint hide-n" style="font-size:12px">plan_id ${esc(c.planId)} · release_id ${esc(c.release)} · batch ${esc(c.batch)}</span></div><div class="bd">
    <div class="path" style="margin-bottom:14px"><a class="pn" href="${lnk("products.html#detail")}">${I.build}${esc(d.ctx.product.key)}</a><span class="pa">${I.chev}</span><a class="pn" href="${lnk("releases.html#detail")}">${I.tag}${esc(c.release)}</a><span class="pa">${I.chev}</span><a class="pn" href="${lnk("plans.html#detail")}">${I.flag}${esc(c.plan)}</a><span class="pa">${I.chev}</span><span class="pn on">${I.cycle}This cycle</span></div>
    <div class="fx-r">${c.features.map((f) => L("tree.html", `${I.folder}<b>${esc(f.path)}</b><span class="faint">${f.cases} cases</span>`)).join("")}</div>
  </div></div>`;
  return `${crumbs([productCrumb(d), [esc(c.release), "releases.html#detail"], [esc(c.plan), "plans.html#detail"], ["Cycles", "#list"], [esc(c.name)]])}
  <div class="eyebrow">Cycle · ${esc(c.id)}</div>
  <div class="ph" style="margin-top:6px"><h1>${esc(c.name)}</h1><span class="pill ${closed ? "closed" : "open"}">${closed ? "closed" : "open"}</span><span class="chip mono">${esc(c.release)}</span><span class="chip">${esc(c.env)}</span>
  <div class="actions">${closed ? `<button class="btn">Reopen</button>` : `<button class="btn">${I.plus}Add cases</button><button class="btn">${I.lock}Close cycle</button><a class="btn primary" href="${lnk("run.html")}">${I.run}Run next untested</a>`}</div></div>
  ${closed ? `<div class="banner">${I.lock}<div>Closed by ${esc(person(c.closedBy)[0])}, ${esc(c.closedAt)}. Results are read only; reopening is audited.</div></div>` : ""}${banner}
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
  return modal(`Refresh ${esc(f.key)} to v${f.to}?`, `<p style="margin-top:0">This cycle has ${esc(f.key)} pinned at ${ver(f.from, 1)}. v${f.to} changed:</p>
    <div class="diff card"><div class="bd" style="font-size:13px">Step ${esc(f.step)} expected: <del>${esc(f.before)}</del> <ins>${esc(f.after)}</ins><br>Tags: <ins>${esc(f.tagsAdded.join(", "))}</ins></div></div>
    <p class="muted" style="font-size:13px">Allowed only before the first result. The refresh is recorded in the audit log as <code>cycle_case.refresh_version</code>.</p>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-hash="refresh-409">Refresh to v${f.to}</button>`);
};
const refused = (d) => `<div class="banner err">${I.warn}<div style="flex:1;min-width:0"><b>Not refreshed.</b> A result came in before the refresh:
<pre class="raw">${esc(d.error)}</pre></div></div>`;

const empty = (d) => head(d) + `<div class="card"><div class="empty"><div class="ill">${I.cycle}</div><h3>No cycles yet</h3><div>A cycle pins the current version of each case so results stay comparable.<br>Start from a release to get one cycle per affected feature.</div>
    <button class="btn primary" data-hash="bulk-pick-release">Bulk cycle from a release</button> <button class="btn" data-hash="new-cycle">New cycle</button></div></div>`;

export default { nav: "cycles", default: "list",
  /* buttons that open another state, and the create-cycle confirmation */
  after: (main, id, d) => {
    main.querySelectorAll("[data-hash]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.hash; }));
    main.querySelectorAll("[data-create]").forEach((b) => b.addEventListener("click", () => toast(`<div><b>Cycle created.</b> <span class="muted">${d.draft.total} cases pinned.</span></div>`)));
  },
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
