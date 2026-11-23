/* Versions (releases) adapter (docs/app-api-contract.md §2): releases_list, releases_get, releases_create,
   releases_update, releases_set_features and reports_release, with features_list for the feature picker and
   plans_list and cycles_list matched on release_id. Maps the API onto the shapes views/releases.js renders. */
import { all, get, org, patch, post, put } from "../api.js";
import { day, flatten, plain, results, today, when } from "./map.js";

const plural = (n, one) => `${n} ${n === 1 ? one : one + "s"}`;
const DETAIL_UI = ["set-features", "features-saved", "released"];
/* a plan's scope in words: its features, else its cases */
const scope = (p) => {
  const nf = p.entries.filter((e) => e.feature_id).length;
  return nf ? plural(nf, "feature") : plural(p.entries.reduce((n, e) => n + (e.cases ?? (e.case_id ? 1 : 0)), 0), "case");
};

/* the product the view is about: the one in the context (?product=), or the release's own */
function productOf(ctx, productId) {
  const p = (productId && ctx.products.find((x) => x.id === productId)) || ctx.product;
  if (!p) throw new Error("This org has no products yet.");
  return { id: p.id, key: p.key, name: p.name };
}

/* three suggested target dates, Fridays 2, 5 and 8 weeks after the latest target (or today) */
function targets(releases) {
  const last = releases.filter((r) => r.target_date).sort((a, b) => (a.target_date < b.target_date ? 1 : -1))[0];
  const base = new Date((last ? last.target_date : today()) + "T00:00:00");
  return [2, 5, 8].map((weeks) => {
    const d = new Date(base);
    d.setDate(d.getDate() + weeks * 7 + ((5 - d.getDay() + 7) % 7));
    return { v: today(d), label: day(today(d), { day: true }), hint: last ? `${weeks} weeks after ${last.version}` : `in ${weeks} weeks` };
  });
}

async function list(at, product, ui) {
  const [releases, report, plans, cycles] = await Promise.all([
    all(at("products", product.key, "releases")),
    get(at("products", product.key, "report")),
    all(at("products", product.key, "plans")),
    all(at("products", product.key, "cycles"))
  ]);
  const totals = Object.fromEntries(report.releases.map((t) => [t.release.id, t.counts]));
  const versions = releases.map((r) => ({
    id: r.id, ver: r.version, status: r.status, when: when(r), features: r.feature_ids.length,
    plans: plans.filter((p) => p.release_id === r.id).length, cycles: cycles.filter((c) => c.release_id === r.id).length,
    results: results(totals[r.id]), summary: r.name
  }));
  const data = {
    product, versions, noVersionsFor: product.key,
    draft: {
      ver: "", status: "planned", name: "", target: "none", copyFrom: "none", notes: "",
      targets: targets(releases), copyable: releases.map((r) => r.version)
    }
  };
  if (ui === "new") return { state: "new", data };
  return { state: versions.length ? "list" : "empty", data };
}

async function detail(at, ctx, id, ui) {
  const r = await get(at("releases", id));
  const product = productOf(ctx, r.product_id);
  const [report, tree, plans, cycles] = await Promise.all([
    get(at("releases", id, "report")),
    get(at("products", product.key, "features")),
    all(at("products", product.key, "plans")),
    all(at("products", product.key, "cycles"))
  ]);
  const mine = { plans: plans.filter((p) => p.release_id === id), cycles: cycles.filter((c) => c.release_id === id) };
  const c = report.counts;
  const executed = (c.total || 0) - (c.untested || 0);
  const detail = {
    id: r.id, ver: r.version, name: r.name, status: r.status, target: r.target_date ? day(r.target_date, { day: true }) : "not set",
    notes: plain(r.notes), features: r.feature_ids.length, plans: mine.plans.length, cycles: mine.cycles.length,
    kpis: {
      inScope: report.kpis.cases, fromFeatures: r.feature_ids.length,
      executedPct: c.total ? Math.round((executed / c.total) * 100) : 0, executed, cycleCases: c.total || 0,
      passPct: report.kpis.success_rate ?? 0
    },
    tree: flatten(tree.items).map((f) => ({ id: f.id, path: f.path, cases: f.total_case_count, inVersion: r.feature_ids.includes(f.id), sub: f.depth > 0 })),
    testPlans: mine.plans.map((p) => ({ id: p.id, name: p.name, status: p.status, scope: scope(p) })),
    cycleList: mine.cycles.map((cy) => ({ id: cy.id, name: cy.name, status: cy.status })),
    untested: c.untested || 0, openCycles: mine.cycles.filter((cy) => cy.status === "open").length
  };
  return { state: DETAIL_UI.includes(ui) ? ui : "detail", data: { product, detail } };
}

/* params: the URL's query (id, product) and ui, the hash's UI state ("new", "set-features", ...). */
export async function load(params, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  if (params.id) return detail(at, ctx, params.id, params.ui);
  return list(at, productOf(ctx), params.ui);
}

const at = (ctx) => (...rest) => org(ctx.org.id, ...rest);

/* The view's writes; each resolves to the ReleaseOut the server returns. */
export const actions = {
  /* form: { ver, name, status, target ("none" or YYYY-MM-DD), copyFrom ("none" or a version), notes } */
  async create(form, ctx, productKey) {
    const path = at(ctx);
    const r = await post(path("products", productKey, "releases"), {
      version: form.ver, name: form.name, status: form.status,
      target_date: form.target && form.target !== "none" ? form.target : null,
      notes: form.notes ? { markdown: form.notes } : undefined
    });
    if (!form.copyFrom || form.copyFrom === "none") return r;
    const from = (await all(path("products", productKey, "releases"))).find((x) => x.version === form.copyFrom);
    return from && from.feature_ids.length ? put(path("releases", r.id, "features"), { feature_ids: from.feature_ids }) : r;
  },
  /* change: any of ReleaseUpdate's fields ({ status: "released", released_at }, { name }, ...) */
  update: (id, change, ctx) => patch(at(ctx)("releases", id), change),
  setFeatures: (id, featureIds, ctx) => put(at(ctx)("releases", id, "features"), { feature_ids: featureIds })
};
