/* Test plans adapter (docs/app-api-contract.md §7): plans_list (name search is the server's q), plans_get,
   plans_create, plans_update, plans_add_entries, plans_remove_entry, plans_resolve and cycles_create from a plan,
   with releases_list, features_list, cases_get, cycles_list and cycles_preview for the labels, the counts and the
   new-cycle form. Each entry's `cases` and `new_cases` (F3) give the resolution counts. Maps the API onto the
   shapes views/plans.js renders. */
import { all, del, get, org, page, patch, post } from "../api.js";
import { flatten, results } from "./map.js";

const DEFAULT_STATUS = ["active", "draft"];
const STATUSES = ["draft", "active", "archived"];
const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const kindOf = (e) => (e.feature_id ? "feature" : e.case_id ? "case" : "query");
const sum = (xs, f) => xs.reduce((n, x) => n + (f(x) || 0), 0);
const total = (counts) => Object.values(counts || {}).reduce((n, v) => n + v, 0);
const newest = (cycles) => [...cycles].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));

/* a plan query ({tags, priority, type, automation}) as one line, "tags: visa AND priority: high" */
export const queryText = (q) => Object.entries(q || {}).filter(([, v]) => v && v.length).map(([k, v]) => `${k}: ${v.join(" OR ")}`).join(" AND ");
/* the reverse, for the query a person types; unknown keys are the server's to refuse */
export const parseQuery = (text) => Object.fromEntries(String(text).split(/\s+AND\s+/i).map((part) => part.split(":"))
  .filter((kv) => kv.length === 2 && kv[0].trim() && kv[1].trim())
  .map(([k, v]) => [k.trim(), v.split(/\s+OR\s+|,/i).map((x) => x.trim()).filter(Boolean)]));

/* "3 features · 1 query", or "18 cases picked" when the plan names cases only */
function scope(p) {
  const n = { feature: 0, case: 0, query: 0 };
  for (const e of p.entries) n[kindOf(e)] += 1;
  const parts = [n.feature ? plural(n.feature, "feature") : "", n.query ? plural(n.query, "query", "queries") : ""].filter(Boolean);
  if (n.case) parts.push(parts.length ? plural(n.case, "case") : `${plural(n.case, "case")} picked`);
  return parts.join(" · ") || "no entries yet";
}
/* the live cases a plan resolves to: each entry's new_cases sum to the plans_resolve total */
const caseCount = (p) => sum(p.entries, (e) => e.new_cases);

function draft(ctx, releases, cur) {
  const v = cur || null;
  return {
    name: "", product: ctx.product.key, version: v ? v.id : "none", allFeatures: !!(v && v.feature_ids.length),
    featureCount: v ? v.feature_ids.length : 0,
    versions: releases.map((r) => ({ id: r.id, ver: r.version, status: r.status.replace("_", " "), features: r.feature_ids.length }))
  };
}

async function list(at, ctx, params) {
  const key = ctx.product.key;
  const q = (params.q || "").trim();
  const status = params.status ? params.status.split(",").filter((s) => STATUSES.includes(s)) : DEFAULT_STATUS;
  const versionFilter = params.version || "all";
  const [found, every, releases, cycles] = await Promise.all([
    all(at("products", key, "plans"), { q, include_archived: status.includes("archived") }),
    page(at("products", key, "plans"), { include_archived: true, limit: 1 }),
    all(at("products", key, "releases")),
    all(at("products", key, "cycles"))
  ]);
  const ver = Object.fromEntries(releases.map((r) => [r.id, r.version]));
  /* the version and status filters are the app's, on the whole list (contract §7) */
  const shown = found.filter((p) => status.includes(p.status) && (versionFilter === "all" || ver[p.release_id] === versionFilter));
  const plans = shown.map((p) => {
    const last = newest(cycles.filter((c) => c.plan_id === p.id))[0];
    const n = caseCount(p);
    return { id: p.id, name: p.name, status: p.status, version: p.release_id ? ver[p.release_id] : "any version", scope: scope(p), cases: plural(n, "case"), results: last ? results(last.counts) : {} };
  });
  const cur = releases.find((r) => ctx.version && r.id === ctx.version.id);
  const data = { q, total: every.total, versionFilter, statusFilter: status, plans, detail: { entries: [] }, draft: draft(ctx, releases, cur) };
  if (params.ui === "new") return { state: "new", data };
  if (q) return { state: plans.length ? "search" : "search-empty", data };
  if (!every.total) return { state: "empty", data };
  return { state: params.ui === "search-cleared" ? "search-cleared" : "list", data };
}

async function detail(at, ctx, params) {
  const p = await get(at("plans", params.id));
  const product = ctx.products.find((x) => x.id === p.product_id) || ctx.product;
  const [tree, releases, cycles, resolved, caseRows] = await Promise.all([
    get(at("products", product.key, "features")),
    all(at("products", product.key, "releases")),
    all(at("products", product.key, "cycles")),
    get(at("plans", p.id, "resolve")),
    Promise.all(p.entries.filter((e) => e.case_id).map((e) => get(at("cases", e.case_id))))
  ]);
  /* a draft or archived plan can't start a cycle, so only an active one has a preview (its deprecated count) */
  const preview = p.status === "active" ? await post(at("products", product.key, "cycles", "preview"), { plan_id: p.id }) : null;
  const features = flatten(tree.items);
  const path = Object.fromEntries(features.map((f) => [f.id, f.path]));
  const cases = Object.fromEntries(caseRows.map((c) => [c.id, c]));
  const rel = releases.find((r) => r.id === p.release_id) || null;
  const label = (e) => {
    const k = kindOf(e);
    if (k === "feature") return path[e.feature_id] || e.feature_id;
    if (k === "case") return cases[e.case_id] ? `${cases[e.case_id].key} · ${cases[e.case_id].title}` : e.case_id;
    return queryText(e.query);
  };
  const meta = (e) => {
    const k = kindOf(e);
    if (k === "feature") return `all its cases, resolved when the cycle starts · now ${e.cases}`;
    if (k === "case") return `single case${cases[e.case_id] ? ` · v${cases[e.case_id].current_version} now` : ""}`;
    return `matches ${e.cases} · ${e.cases - e.new_cases} already in an entry above`;
  };
  const entries = p.entries.map((e) => ({ id: e.id, kind: kindOf(e), label: label(e), meta: meta(e) }));
  const of = (k) => p.entries.filter((e) => kindOf(e) === k);
  const mine = newest(cycles.filter((c) => c.plan_id === p.id));
  /* a cycle just made from this plan (?cycle=) leads the list */
  const made = params.cycle ? mine.find((c) => c.id === params.cycle) : null;
  const ordered = made ? [made, ...mine.filter((c) => c !== made)] : mine;
  const first = resolved.items[0];
  const envs = [...new Set(newest(cycles).map((c) => c.environment).filter(Boolean))];
  const env = (mine.find((c) => c.environment) || {}).environment || envs[0] || "new";
  const d = {
    product: { id: product.id, key: product.key, name: product.name },
    detail: {
      id: p.id, name: p.name, status: p.status, releaseId: p.release_id || null,
      version: rel ? rel.version : "any version", versionStatus: rel ? rel.status : "",
      entries,
      resolve: {
        features: of("feature").length, featureCases: sum(of("feature"), (e) => e.new_cases),
        queryNew: sum(of("query"), (e) => e.new_cases), cases: of("case").length,
        pinned: resolved.items.length, example: first ? { key: first.key, ver: first.version } : null
      },
      cycles: ordered.map((c) => ({ id: c.id, name: c.name, status: c.status, pinned: total(c.counts) })),
      latest: ordered.length ? { env: ordered[0].environment || "", results: results(ordered[0].counts) } : null
    },
    features: features.map((f) => ({ id: f.id, path: f.path })),
    newCycle: {
      environments: envs, env, name: env === "new" ? p.name : `${p.name} · ${env}`,
      resolved: p.entries.map((e) => ({ label: kindOf(e) === "query" ? `Query: ${label(e)}` : kindOf(e) === "case" ? (cases[e.case_id] || {}).key || e.case_id : label(e), count: e.new_cases, unit: kindOf(e) === "query" ? "new" : "" })),
      deprecated: preview ? preview.skipped.deprecated || 0 : null, skipDeprecated: true
    }
  };
  if (made) return { state: "cycle-created", data: d };
  return { state: ["edit", "create-cycle"].includes(params.ui) ? params.ui : "detail", data: d };
}

/* params: the URL's query (id, q, status, version, cycle) and ui, the hash's UI state ("new", "edit", ...). */
export async function load(params, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  if (params.id) return detail(at, ctx, params);
  if (!ctx.product) throw new Error("This org has no products yet.");
  return list(at, ctx, params);
}

const at = (ctx) => (...rest) => org(ctx.org.id, ...rest);
/* an entry the form adds: { feature_id } | { case_id } (a case key or id) | { query: {...} } | { release_id } */
async function apply(path, planId, add, remove) {
  let p = null;
  for (const id of remove || []) p = await del(path("plans", planId, "entries", id));
  if (add && add.length) p = await post(path("plans", planId, "entries"), { entries: add });
  return p || get(path("plans", planId));
}

/* The view's writes; each resolves to the server's object (PlanOut or CycleOut). */
export const actions = {
  /* form: { name, version ("none" or a release id), allFeatures (bool), entries: [entry] } */
  async create(form, ctx, productKey) {
    const path = at(ctx);
    const release = form.version && form.version !== "none" ? form.version : null;
    const p = await post(path("products", productKey, "plans"), { name: form.name, release_id: release });
    const add = [...(form.allFeatures && release ? [{ release_id: release }] : []), ...(form.entries || [])];
    return add.length ? apply(path, p.id, add, []) : p;
  },
  /* change: any of PlanUpdate's fields ({ status: "active" }, { name }, ...) */
  update: (id, change, ctx) => patch(at(ctx)("plans", id), change),
  /* edits: { add: [entry], remove: [entry id] }; removals first, then one add call */
  saveEntries: (id, edits, ctx) => apply(at(ctx), id, edits.add, edits.remove),
  /* form: { name, environment } */
  createCycle: (planId, form, ctx, productKey) => post(at(ctx)("products", productKey, "cycles"), { plan_id: planId, name: form.name, environment: form.environment || null })
};
