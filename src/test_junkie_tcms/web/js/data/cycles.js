/* Cycles adapter (docs/app-api-contract.md §8): cycles_list (the status tabs are the server's status filter),
   cycles_get, cycles_create, cycles_preview, cycles_close, cycles_reopen, cycles_bulk_create, cycle_batches_get,
   cycle_cases_list, cycle_cases_refresh_version and results_list, with releases_list, plans_list, features_list,
   members_list, actors_list and cases_version_get for names, pickers and the refresh diff. Maps the API onto the
   shapes views/cycles.js renders. Not served yet (F4), so left out: a batch's "created by", "closed by", the bulk
   name pattern, per-cycle assignee and per-feature counts, skipping drafts. */
import { all, get, org, page, post } from "../api.js";
import { day, flatten, plain, results } from "./map.js";

const LIST_UI = ["new-cycle", "bulk-pick-release", "bulk-preview"];
const STATUSES = ["open", "closed", "all"];
const sum = (c) => Object.values(c || {}).reduce((a, b) => a + b, 0);
/* an ISO time as "Fri Nov 13, 9:40 AM" in the browser's zone */
const stamp = (iso) => (iso ? `${day(iso, { day: true })}, ${new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}` : "");

function productOf(ctx, productId) {
  const p = (productId && ctx.products.find((x) => x.id === productId)) || ctx.product;
  if (!p) throw new Error("This org has no products yet.");
  return { id: p.id, key: p.key, name: p.name };
}

/* an actor id as the { kind, name } the views draw: a person by id (ui.js person() names them), else its name */
function who(directory, id) {
  if (!id) return null;
  const a = directory.actors.find((x) => x.id === id);
  if (!a || a.kind === "user") return { kind: "person", name: id };
  return { kind: "agent", name: a.name };
}

const releaseRow = (r) => ({
  id: r.id, ver: r.version, name: r.name, status: r.status, features: r.feature_ids.length,
  date: day(r.status === "released" ? r.released_at : r.target_date, { day: true }) || "no date"
});

/* people (members) and enabled agents a cycle can be assigned to */
function assignees(members, directory) {
  return [
    ...members.map((m) => ({ v: m.actor_id, kind: "person", role: m.role })),
    ...directory.actors.filter((a) => a.kind === "agent" && !a.disabled).map((a) => ({ v: a.id, kind: "agent", name: a.name }))
  ];
}

/* the environment labels the listed cycles use (the API keeps environment as a free label) */
const envsOf = (cycles) => [...new Set(cycles.map((c) => c.environment).filter(Boolean))].map((e) => ({ v: e, label: e, hint: "" }));

/* the product's feature tree, one group per top-level feature: it and everything under it */
const groupsOf = (tree) => tree.items.map((top) => ({
  name: top.name,
  features: flatten([top]).map((f) => ({ v: f.id, label: f.path, cases: f.total_case_count }))
}));

/* the list rows: each batch's cycles together under one batch row, at the place of its first cycle */
async function rowsOf(path, cycles, ver, directory) {
  const ids = [...new Set(cycles.map((c) => c.batch_id).filter(Boolean))];
  const batches = Object.fromEntries((await Promise.all(ids.map((id) => get(path("cycle-batches", id))))).map((b) => [b.id, b]));
  const row = (c) => ({
    id: c.id, name: c.name, release: ver[c.release_id] || "", env: c.environment || "", status: c.status,
    assignee: who(directory, c.default_assignee_actor_id), results: results(c.counts), inBatch: !!c.batch_id
  });
  const out = [];
  const done = new Set();
  for (const c of cycles) {
    if (!c.batch_id) { out.push(row(c)); continue; }
    if (done.has(c.batch_id)) continue;
    done.add(c.batch_id);
    const b = batches[c.batch_id];
    out.push({ kind: "batch", id: b.id, name: b.name, per: b.mode, cycles: b.cycles.length, on: day(b.created_at, { day: true }) });
    out.push(...cycles.filter((x) => x.batch_id === c.batch_id).map(row));
  }
  return out;
}

/* the bulk wizard: the release picked (?release=, else the product's current version), one cycle per affected
   feature or per active plan (?per=plans), and the cases the release's features hold */
async function bulkOf(path, product, releases, tree, plans, params, ctx) {
  const pick = releases.find((r) => r.id === params.release) || releases.find((r) => ctx.version && r.id === ctx.version.id)
    || releases.find((r) => r.status !== "released" && r.status !== "cancelled") || releases[0];
  if (!pick) return null;
  const per = params.per === "plans" ? "plans" : "features";
  const features = flatten(tree.items);
  const active = plans.filter((p) => p.release_id === pick.id && p.status === "active");
  const affected = features.filter((f) => pick.feature_ids.includes(f.id));
  const preview = pick.feature_ids.length
    ? await post(path("products", product.key, "cycles", "preview"), { feature_ids: pick.feature_ids, mode: "manual" })
    : { total: 0 };
  const rows = per === "plans"
    ? active.map((p) => ({ path: p.name, cases: p.entries.reduce((n, e) => n + (e.new_cases || 0), 0) }))
    : affected.map((f) => ({ path: f.path, cases: null }));
  return {
    release: pick.version, releaseId: pick.id, env: "", per, plans: active.length, featureCount: affected.length,
    cases: preview.total, total: per === "plans" ? rows.reduce((n, r) => n + r.cases, 0) : preview.total, features: rows
  };
}

async function list(path, ctx, params) {
  const product = productOf(ctx);
  const status = STATUSES.includes(params.status) ? params.status : "open";
  const P = (...rest) => path("products", product.key, ...rest);
  const [listed, open, closed, releases, members, directory] = await Promise.all([
    page(P("cycles"), status === "all" ? {} : { status }),
    page(P("cycles"), { status: "open", limit: 1 }),
    page(P("cycles"), { status: "closed", limit: 1 }),
    all(P("releases")),
    all(path("members")),
    get(path("actors"))
  ]);
  const ver = Object.fromEntries(releases.map((r) => [r.id, r.version]));
  const data = {
    product,
    releases: releases.map(releaseRow),
    envs: envsOf(listed.items),
    assignees: assignees(members, directory),
    featureGroups: [],
    tabs: { open: open.total, closed: closed.total },
    filter: { status, release: "any", env: "any", assignee: "any" },
    rows: await rowsOf(path, listed.items, ver, directory),
    error: ""
  };
  const ui = params.ui;
  if (ui === "new-cycle") {
    const tree = await get(P("features"));
    const cur = releases.find((r) => ctx.version && r.id === ctx.version.id);
    data.featureGroups = groupsOf(tree);
    data.draft = { name: "", features: [], release: cur && cur.status !== "released" ? cur.version : "none", env: "", assignee: "none", total: 0, deprecated: 0, archived: 0 };
  }
  if (ui === "bulk-pick-release" || ui === "bulk-preview") {
    const [tree, plans] = await Promise.all([get(P("features")), all(P("plans"))]);
    data.bulk = await bulkOf(path, product, releases, tree, plans, params, ctx);
  }
  if (ui === "bulk-created" && params.batch) {
    const b = await get(path("cycle-batches", params.batch));
    const rows = b.cycles.map((c) => ({ path: c.name, cases: sum(c.counts) }));
    data.bulk = { release: ver[b.release_id] || b.name, releaseId: b.release_id, per: b.mode, features: rows, total: rows.reduce((n, r) => n + r.cases, 0) };
    return { state: "bulk-created", data };
  }
  if (LIST_UI.includes(ui) && (ui === "new-cycle" || data.bulk)) return { state: ui, data };
  return { state: open.total + closed.total ? "list" : "empty", data };
}

/* the confirm dialog's diff between the pinned version and the current one: the first step whose text changed,
   and the tags added; results is how many results the case has, which stay as history after the refresh */
async function refreshOf(path, cc, results) {
  const [from, to] = await Promise.all([
    get(path("cases", cc.case_id, "versions", String(cc.case_version))),
    get(path("cases", cc.case_id, "versions", String(cc.current_version)))
  ]);
  const old = Object.fromEntries(from.steps.map((s) => [s.id, s]));
  const changed = to.steps.find((s) => !old[s.id] || plain(old[s.id].expected) !== plain(s.expected) || plain(old[s.id].action) !== plain(s.action));
  return {
    id: cc.id, key: cc.key, from: cc.case_version, to: cc.current_version, results,
    step: changed ? changed.id : "", before: changed && old[changed.id] ? plain(old[changed.id].expected) : "", after: changed ? plain(changed.expected) : "",
    tagsAdded: to.tags.filter((t) => !from.tags.includes(t))
  };
}

async function detail(path, ctx, params) {
  const c = await get(path("cycles", params.id));
  const product = productOf(ctx, c.product_id);
  const [cases, directory, release, plan] = await Promise.all([
    all(path("cycles", c.id, "cases"), { sort: "position" }),
    get(path("actors")),
    c.release_id ? get(path("releases", c.release_id)) : null,
    c.plan_id ? get(path("plans", c.plan_id)) : null
  ]);
  // each case's attempts: the result count, and the last one's defect or comment as its note
  const attempts = await Promise.all(cases.map((x) => (x.last_result_at ? all(path("cycle-cases", x.id, "results")) : [])));
  const feature = c.feature_id ? flatten((await get(path("products", product.key, "features"))).items).find((f) => f.id === c.feature_id) : null;
  const cycle = {
    id: c.id, name: c.name, status: c.status, env: c.environment || "",
    release: release ? release.version : "", releaseId: c.release_id || "", plan: plan ? plan.name : "", planId: c.plan_id || "", batch: c.batch_id || "",
    closedAt: stamp(c.closed_at), counts: c.counts,
    features: feature ? [{ id: feature.id, path: feature.path, cases: sum(c.counts) }] : [],
    cases: cases.map((x, i) => {
      const last = attempts[i][attempts[i].length - 1];
      const defect = last && last.defects.find((d) => d.key || d.url);
      return {
        id: x.id, key: x.key, title: x.title, pinned: x.case_version, newer: x.current_version > x.case_version ? x.current_version : 0,
        status: x.status, assignee: who(directory, x.assignee_actor_id), hasResult: !!x.last_result_at,
        note: last ? (defect ? defect.key || defect.url : plain(last.comment)) : "", attempt: attempts[i].length
      };
    })
  };
  const data = { product, cycle, error: "" };
  if (params.ui === "refresh-confirm" && c.status === "open") {
    // the API re-pins any case of an open cycle, with or without results (cycle_cases_refresh_version)
    const asked = cases.findIndex((x) => x.id === params.cc);
    const i = asked >= 0 ? asked : cases.findIndex((x) => x.current_version > x.case_version);
    const cc = cases[i];
    if (cc && cc.current_version > cc.case_version) {
      data.refresh = await refreshOf(path, cc, attempts[i].length);
      return { state: "refresh-confirm", data };
    }
  }
  return { state: c.status === "closed" ? "closed" : "detail", data };
}

/* params: the URL's query (id: a cycle; status: the tab; release, per, batch: the bulk wizard; cc: the case to
   refresh) and ui, the hash's UI state. */
export async function load(params, ctx) {
  const path = (...rest) => org(ctx.org.id, ...rest);
  if (params.id) return detail(path, ctx, params);
  return list(path, ctx, params);
}

const pathOf = (ctx) => (...rest) => org(ctx.org.id, ...rest);

/* The view's writes; each resolves to what the server returns. */
export const actions = {
  /* form: { name, featureIds, releaseId (or null), environment (or null), assigneeId (or null) } -> CycleOut */
  create: (form, ctx, productKey) => post(pathOf(ctx)("products", productKey, "cycles"), {
    name: form.name, feature_ids: form.featureIds, release_id: form.releaseId || null, environment: form.environment || null,
    default_assignee_actor_id: form.assigneeId || null, mode: "manual"
  }),
  /* what a cycle from these features would pin: CyclePreviewOut { total, skipped: { archived, deprecated } } */
  preview: (featureIds, ctx, productKey) => post(pathOf(ctx)("products", productKey, "cycles", "preview"), { feature_ids: featureIds, mode: "manual" }),
  /* one cycle per affected feature (per: "features") or active plan ("plans") of the release -> CycleBatchOut */
  bulk: (releaseId, form, ctx) => post(pathOf(ctx)("releases", releaseId, "cycles", "bulk"), { mode: form.per, environment: form.environment || null }),
  close: (id, ctx) => post(pathOf(ctx)("cycles", id, "close")),
  reopen: (id, ctx) => post(pathOf(ctx)("cycles", id, "reopen")),
  /* re-pin a cycle case to its case's current version -> CycleCaseOut */
  refresh: (cycleCaseId, ctx) => post(pathOf(ctx)("cycle-cases", cycleCaseId, "refresh-version"))
};
