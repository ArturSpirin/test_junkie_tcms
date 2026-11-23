/* Reports adapter (docs/app-api-contract.md §11): reports_org, reports_product (the product-wide report, no
   release), reports_release and reports_feature, each for the period (from, to, tz); releases_list for the release
   picker and "since last release", features_list for a feature's path, cycles_list for a release's cycle count.
   Maps the API onto the shapes views/reports.js renders. */
import { all, get, org } from "../api.js";
import { current, day, flatten, results, today, when } from "./map.js";

const RANGES = { today: 0, "7d": 6, "14d": 13, "30d": 29 };
const KINDS = ["success", "fail", "error", "ignore", "skip", "cancel"];
const VERDICT = { ready: "ready", at_risk: "at risk", in_progress: "in progress", not_started: "not started" };
const PRODUCT_UI = ["pick-release", "bar-hover"];

const daysAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return today(d); };
const sum = (c) => KINDS.reduce((n, k) => n + (c[k] || 0), 0);
const full = (c) => Object.fromEntries([...KINDS, "untested"].map((k) => [k, (c && c[k]) || 0]));
const stamp = (iso) => `${day(iso, { day: true })}, ${new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
const tz = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

/* the period: ?range= (today, 7d, 14d, 30d; 30d by default), ?range=custom&from=&to=, or ?range=rel, from the
   latest release's released_at to today */
async function periodOf(at, ctx, params) {
  const value = params.range || "30d";
  let from, to = today();
  if (value === "custom" && params.from) { from = params.from; to = params.to || to; }
  else if (value === "rel") {
    const keys = params.level && params.level !== "org" ? [productOf(ctx, params).key] : ctx.products.map((p) => p.key);
    const released = (await Promise.all(keys.map((k) => all(at("products", k, "releases"))))).flat().map((r) => r.released_at).filter(Boolean).sort();
    from = released.length ? today(new Date(released[released.length - 1])) : daysAgo(RANGES["30d"]);
  } else from = daysAgo(RANGES[value] ?? RANGES["30d"]);
  const preset = value in RANGES;
  const label = preset ? (value === "today" ? "today" : `last ${RANGES[value] + 1} days`) : `${day(from)} – ${day(to)}`;
  return {
    view: preset ? { value, open: params.ui === "period-custom" } : { value: "custom", applied: true, from, to, open: params.ui === "period-custom" },
    keep: { range: preset ? value : value === "rel" ? "rel" : "custom", from: preset || value === "rel" ? null : from, to: preset || value === "rel" ? null : to },
    label, query: { from, to, tz: tz() }
  };
}

function productOf(ctx, params) {
  const p = ctx.products.find((x) => x.key === params.product || x.id === params.product) || ctx.product;
  if (!p) throw new Error("This org has no products yet.");
  return { id: p.id, key: p.key, name: p.name, cases: p.cases };
}

async function orgReport(at, ctx, params, period) {
  const r = await get(at("report"), period.query);
  const days = r.trend.days.map((x) => ({ date: x.date, ...Object.fromEntries(KINDS.map((k) => [k, x[k] || 0])) }));
  const totals = Object.fromEntries(KINDS.map((k) => [k, days.reduce((n, x) => n + x[k], 0)]));
  const peak = r.trend.peak_day ? days.findIndex((x) => x.date === r.trend.peak_day.date) : -1;
  const data = {
    period: period.view, periodKeep: period.keep, periodLabel: period.label, product: ctx.product ? productOf(ctx, params) : null,
    org: {
      kpis: { readyCases: r.kpis.ready_cases, products: r.kpis.products, successPct: r.kpis.success_rate, automatedPct: r.kpis.automated_pct, openCycles: r.kpis.open_cycles, untested: r.kpis.open_untested },
      trend: { totals, results: r.trend.total, peakDay: r.trend.peak_day ? day(r.trend.peak_day.date, { day: true }) : "–", byAgentsPct: r.trend.by_agents_pct, days },
      products: r.products.map((p) => ({ id: p.product_id, key: p.product_key, name: p.name, cases: p.cases, automatedPct: p.automated_pct, results: results(p.results), successPct: p.success_rate, openCycles: p.open_cycles }))
    },
    pinDay: peak >= 0 ? peak : days.length - 1
  };
  if (params.ui === "org-hover" || params.ui === "period-custom") return { state: params.ui, data };
  return { state: "org", data };
}

/* a feature row's drift in words */
const driftNote = (f) => {
  const d = f.drifted || [];
  if (!f.drift) return "";
  if (f.drift === 1 && d.length) return `${d[0].key} v${d[0].current_version} is newer than pinned v${d[0].ran_version}`;
  return `${f.drift} cases edited after their result`;
};
const featureRow = (f) => ({ id: f.feature_id, path: f.path || f.name, cases: f.counts.total || 0, results: results(f.counts), drift: f.drift || 0, driftNote: driftNote(f), readiness: VERDICT[f.verdict] || "not started" });

function releaseOption(r, cycles) {
  const n = cycles.filter((c) => c.release_id === r.id).length;
  const date = r.status === "released" && r.released_at ? `released ${day(r.released_at, { day: true })}` : r.target_date ? `due ${day(r.target_date, { day: true })}` : "";
  const hint = [r.status === "released" ? "" : r.status, date, n ? `${n} release cycle${n === 1 ? "" : "s"}` : r.status === "released" ? "" : "no cycles yet"].filter(Boolean).join(" · ");
  return { id: r.id, ver: r.version, name: r.name, status: r.status, due: r.target_date && r.status !== "released" ? day(r.target_date, { day: true }) : "", hint, when: when(r) };
}

async function productReport(at, ctx, params, period) {
  const product = productOf(ctx, params);
  const [releases, cycles, whole] = await Promise.all([
    all(at("products", product.key, "releases")),
    all(at("products", product.key, "cycles")),
    get(at("products", product.key, "report"), period.query)
  ]);
  const picked = params.release === "none" ? null
    : params.release ? releases.find((r) => r.id === params.release) || await get(at("releases", params.release))
    : current(releases);
  const rep = picked ? await get(at("releases", picked.id, "report"), period.query) : whole.whole;
  const k = rep.kpis;
  const features = (picked ? rep.features.filter((f) => f.in_release) : rep.features).map(featureRow);
  const drifted = rep.features.flatMap((f) => f.drifted || [])[0];
  const options = releases.map((r) => releaseOption(r, cycles));
  const mine = picked ? options.find((o) => o.id === picked.id) : null;
  const data = {
    period: period.view, periodKeep: period.keep, periodLabel: period.label, product,
    release: {
      id: picked ? picked.id : null, ver: picked ? picked.version : "", name: picked ? picked.name : "", due: mine ? mine.due : "",
      cycles: picked ? cycles.filter((c) => c.release_id === picked.id).length : null, open: params.ui === "pick-release",
      kpis: { cases: k.cases, ran: k.ran, ranPct: k.cases ? Math.round((k.ran / k.cases) * 100) : 0, fail: k.fail, error: k.error, skip: k.skip, drift: k.drift },
      latest: results(rep.counts), driftExample: drifted ? { key: drifted.key, from: drifted.ran_version, to: drifted.current_version } : null,
      releases: options, features
    }
  };
  if (!sum(whole.whole.counts) && !sum(rep.counts)) return { state: "empty", data };
  return { state: PRODUCT_UI.includes(params.ui) ? params.ui : "product", data };
}

async function featureReport(at, ctx, params, period) {
  const product = productOf(ctx, params);
  const [tree, releases] = await Promise.all([get(at("products", product.key, "features")), all(at("products", product.key, "releases"))]);
  const nodes = flatten(tree.items);
  const node = params.feature ? nodes.find((f) => f.id === params.feature) : nodes[0];
  if (!node && params.feature) await get(at("features", params.feature)); // an unknown id: the API's 404
  if (!node) throw new Error(`${product.key} has no features yet.`);
  const release = params.release && params.release !== "none" ? releases.find((r) => r.id === params.release) : null;
  const items = [];
  let rep, cursor = null;
  do {
    rep = await get(at("features", node.id, "report"), { ...period.query, release: release ? release.id : undefined, limit: 200, cursor });
    items.push(...rep.items);
    cursor = rep.next_cursor;
  } while (cursor);
  const by = (a) => (a ? { kind: a.kind === "agent" ? "agent" : "person", id: a.name } : null);
  const cases = items.map((c) => {
    const lr = c.last_result;
    const defect = (c.defects || []).find((x) => x.key || x.url);
    const attempt = c.attempt || (lr && lr.attempt) || 0;
    return {
      id: c.id, key: c.key, title: c.title, ranOn: c.ran_version ?? (lr ? lr.version : c.current_version), current: c.current_version, result: c.status,
      by: by(c.actor || (lr && lr.actor)), when: c.last_result_at ? stamp(c.last_result_at) : lr ? stamp(lr.at) : "",
      note: defect ? defect.key || defect.url : attempt > 1 ? `attempt ${attempt}` : "", noteKind: defect ? "issue" : attempt > 1 ? "attempt" : "", noteHref: defect && defect.url ? defect.url : "",
      why: c.comment || ""
    };
  });
  const data = {
    period: period.view, periodKeep: period.keep, periodLabel: period.label, product,
    release: { id: release ? release.id : null, ver: release ? release.version : "" },
    feature: {
      id: node.id, path: node.path, name: node.name,
      kpis: { cases: rep.kpis.cases, results: full(rep.counts), successPct: rep.kpis.success_rate_last5, drift: rep.kpis.drift },
      cases,
      history: rep.history.map((h) => ({ ver: h.release_version || "no version", env: h.environment || "", when: day(h.at), results: results(h.counts), successPct: h.success_rate }))
    }
  };
  return { state: "feature", data };
}

/* params: the URL's query (level: org, product or feature; product, release ("none" for the whole product),
   feature, range, from, to) and ui ("org-hover", "period-custom", "pick-release", "bar-hover"). */
export async function load(params, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  const period = await periodOf(at, ctx, params);
  if (params.level === "feature") return featureReport(at, ctx, params, period);
  if (params.level === "product") return productReport(at, ctx, params, period);
  return orgReport(at, ctx, params, period);
}

/* Reports only read: the level, period and release controls are links that load again (views/reports.js). */
export const actions = {};
