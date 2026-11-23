/* Products adapter (docs/app-api-contract.md §1): products_list (name search is the server's q), products_get,
   products_create, with releases, reports and plans for the cards and the detail. Maps the API onto the shapes
   views/products.js renders. */
import { all, get, org, page, post } from "../api.js";
import { current, flatten, markCls, plain, results, when } from "./map.js";

const EVERY_STATUS = ["planned", "in_progress", "released", "cancelled"];
const pill = (s) => s.replace("_", " ");

/* releases (ReportRelease or ReleaseOut) as the card's "latest" chip */
const latest = (rels) => {
  const r = current(rels);
  return r ? `${r.version} ${pill(r.status)}` : "No versions yet";
};

function card(x, row) {
  const rels = row ? row.releases : [];
  const cur = current(rels.map((t) => t.release));
  const totals = cur && rels.find((t) => t.release.id === cur.id);
  return {
    id: x.id, key: x.key, name: x.name, markCls: markCls(x.key), desc: plain(x.description),
    features: x.feature_count, cases: x.case_count, versions: rels.length,
    results: totals ? results(totals.counts) : {}, latest: latest(rels.map((t) => t.release))
  };
}

async function detail(at, id) {
  const p = await get(at("products", id));
  const [releases, report, tree, plans, cycles, org] = await Promise.all([
    all(at("products", p.key, "releases")),
    get(at("products", p.key, "report")),
    get(at("products", p.key, "features")),
    all(at("products", p.key, "plans")),
    all(at("products", p.key, "cycles")),
    get(at("report"), { release_status: EVERY_STATUS })
  ]);
  const features = flatten(tree.items);
  const ver = Object.fromEntries(releases.map((r) => [r.id, r.version]));
  const totals = Object.fromEntries(report.releases.map((t) => [t.release.id, t.counts]));
  const row = org.products.find((r) => r.product_id === p.id);
  const changedIn = (f) => (releases.find((r) => r.feature_ids.includes(f.id)) || {}).version || "";
  return {
    id: p.id, key: p.key, name: p.name, desc: plain(p.description), owner: p.owner_actor_id || "",
    kpis: {
      versions: releases.length,
      inProgress: releases.filter((r) => r.status === "in_progress").length,
      planned: releases.filter((r) => r.status === "planned").length,
      features: features.length,
      topLevel: tree.items.length,
      cases: p.case_count,
      automatedPct: row && row.automated_pct !== null ? row.automated_pct : 0,
      plans: plans.length,
      plansActive: plans.filter((pl) => pl.status === "active").length
    },
    versions: releases.map((r) => ({
      id: r.id, ver: r.version, status: r.status, when: when(r, "Due"), features: r.feature_ids.length,
      cycles: cycles.filter((c) => c.release_id === r.id).length, results: results(totals[r.id])
    })),
    features: features.map((f) => ({ id: f.id, path: f.path, cases: f.total_case_count, changedIn: changedIn(f) })),
    plans: plans.map((pl) => {
      const nf = pl.entries.filter((e) => e.feature_id).length;
      const nc = pl.entries.reduce((n, e) => n + (e.cases ?? (e.case_id ? 1 : 0)), 0);
      const meta = [pl.release_id ? ver[pl.release_id] : "Any version", nf ? `${nf} feature${nf === 1 ? "" : "s"}` : "", `${nc} case${nc === 1 ? "" : "s"}`];
      return { id: pl.id, name: pl.name, meta: meta.filter(Boolean).join(" · "), cycles: cycles.filter((c) => c.plan_id === pl.id).length };
    })
  };
}

/* params: the URL's query (id, q, created) and ui, the hash's UI state ("new", "search-cleared"). */
export async function load(params, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  if (params.id) return { state: "detail", data: { detail: await detail(at, params.id) } };
  const q = (params.q || "").trim();
  const [hits, every, report] = await Promise.all([
    page(at("products"), { q, limit: 200 }),
    q ? page(at("products"), { limit: 1 }) : null,
    get(at("report"), { release_status: EVERY_STATUS })
  ]);
  const rows = Object.fromEntries(report.products.map((r) => [r.product_id, r]));
  let products = hits.items.map((x) => card(x, rows[x.id]));
  const total = every ? every.total : hits.total;
  const data = {
    q, total, products, created: null,
    draft: { key: "", name: "", desc: "" },
    copyFrom: ctx.products.map((x) => ({ key: x.key, name: x.name, markCls: x.markCls, features: x.features }))
  };
  if (params.ui === "new" || params.ui === "new-first") return { state: total ? "new" : "new-first", data };
  if (params.created) {
    data.created = products.find((x) => x.key === params.created) || null;
    data.products = products = products.filter((x) => x !== data.created);
    if (data.created) return { state: "created", data };
  }
  if (q) return { state: hits.total ? "search" : "search-empty", data };
  if (!total) return { state: "empty", data };
  return { state: params.ui === "search-cleared" ? "search-cleared" : "list", data };
}

/* The view's writes. form: { key, name, desc, copyFrom ("none" or a product key), firstVersion (bool) }.
   firstVersion adds a planned 1.0.0, as the form's switch says. Resolves to the new ProductOut. */
export const actions = {
  async create(form, ctx) {
    const at = (...rest) => org(ctx.org.id, ...rest);
    const p = await post(at("products"), {
      key: form.key, name: form.name,
      description: form.desc ? { markdown: form.desc } : undefined,
      copy_features_from: form.copyFrom && form.copyFrom !== "none" ? form.copyFrom : undefined
    });
    if (form.firstVersion) await post(at("products", p.key, "releases"), { version: "1.0.0", name: "1.0.0", status: "planned" });
    return p;
  }
};
