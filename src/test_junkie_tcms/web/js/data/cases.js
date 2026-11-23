/* Cases adapter (docs/app-api-contract.md §4): cases_list for the table with the server's own q (a case key or
   number, or text in the title, steps and tags), its filters (feature, status, last result, automation,
   priority), sort, paging and total; features_list for the feature filter. The view never filters or sorts.
   URL: ?q=&feature=<id>&status=a,b&result=a,b&automation=a,b&priority=a,b&sort=&shown=<rows to show>. */
import { get, org, page } from "../api.js";
import { day, flatten } from "./map.js";

export const PAGE = 50;
const SORTS = ["key", "title", "updated", "result", "priority"];
const MULTI = ["status", "result", "automation", "priority"];
const split = (v) => String(v || "").split(",").map((s) => s.trim()).filter(Boolean);

/* the filters a URL holds, as the view's filter object */
export function filtersOf(params) {
  const f = { feature: params.feature ? [params.feature] : [] };
  for (const k of MULTI) f[k] = split(params[k]);
  return f;
}

/* the URL params for a filter object (empty ones dropped by href) */
export function paramsOf(f) {
  const out = { feature: f.feature[0] || null };
  for (const k of MULTI) out[k] = (f[k] || []).join(",") || null;
  return out;
}

/* each page of cases_list until `shown` rows (or the last page): the "Load 50 more" button raises shown */
async function rows(path, query, shown) {
  const items = [];
  let cursor = null, total = 0;
  do {
    const p = await page(path, { ...query, limit: Math.min(200, shown - items.length), cursor });
    items.push(...p.items);
    total = p.total;
    cursor = p.next;
  } while (cursor && items.length < shown);
  return { items, total };
}

/* params: the URL's query (q, filters, sort, shown) and ui ("filter-open", "search-cleared"). */
export async function load(params, ctx) {
  const p = ctx.product;
  if (!p) throw new Error("This org has no products yet. Add a product, then its cases.");
  const at = (...rest) => org(ctx.org.id, ...rest);
  const q = (params.q || "").trim();
  const filter = filtersOf(params);
  const sort = SORTS.includes(params.sort) ? params.sort : "updated";
  const shown = Math.max(PAGE, Math.floor(Number(params.shown)) || PAGE);
  const narrowed = !!(q || filter.feature.length || MULTI.some((k) => filter[k].length));
  const query = { q, sort, feature: filter.feature[0], ...Object.fromEntries(MULTI.map((k) => [k, filter[k]])) };
  const [hits, every, tree] = await Promise.all([
    rows(at("products", p.key, "cases"), query, shown),
    narrowed ? page(at("products", p.key, "cases"), { limit: 1 }) : null,
    get(at("products", p.key, "features"))
  ]);
  const features = flatten(tree.items);
  const path = Object.fromEntries(features.map((f) => [f.id, f.path]));
  const data = {
    q, sort, filter, shown,
    open: params.ui === "filter-open" ? "feature" : null,
    product: { key: p.key, name: p.name },
    total: every ? every.total : hits.total,
    matched: hits.total,
    cases: hits.items.map((c) => ({
      id: c.id, key: c.key, title: c.title, feature: path[c.feature_id] || "", version: c.current_version,
      status: c.status, automation: c.automation, priority: c.priority, tags: c.tags,
      result: c.last_result || "untested", updated: day(c.updated_at)
    })),
    features: features.map((f) => ({ id: f.id, path: f.path, ...(f.depth ? { short: f.name } : {}), cases: f.total_case_count }))
  };
  if (!data.total) return { state: "empty", data };
  if (q) return { state: hits.total ? "search" : "search-empty", data };
  if (data.open) return { state: "filter-open", data };
  if (narrowed) return { state: "filtered", data };
  return { state: params.ui === "search-cleared" ? "search-cleared" : "list", data };
}

/* The list only reads; its writes are on the case view. */
export const actions = {};
