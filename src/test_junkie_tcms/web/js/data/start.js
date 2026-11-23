/* Start a cycle adapter (docs/app-api-contract.md §9 and §10): the wizard reads plans_list, features_list,
   releases_list, members_list (the testers), consumers_list (the machines, each busy one's queue ETA from its
   job's cycle, consumers_jobs and cycles_get) and cycles_preview (the case counts per runner), and starts with
   cycles_create (mode, environment, tester, order, machines, split, retries, queue_when_offline). The live cycle
   reads cycles_get (counts, ETA, stopped), jobs_list and cycle_cases_list, and writes jobs_reassign, jobs_cancel
   and cycles_stop. Maps the API onto the shapes views/start.js renders. */
import { all, get, org, page, post } from "../api.js";
import { flatten, results } from "./map.js";

const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const DONE_JOB = ["done", "failed", "cancelled", "rejected"];
/* a person who can run cases: any member above viewer */
const RUNS = ["tester", "editor", "admin", "owner"];
const MODES = { manual: "manual", auto: "automated", mixed: "both" };
const WIZARD = ["scope", "scope-features", "mode", "mode-manual", "mode-mixed", "manual-ready", "auto-pick", "mixed-pick"];

/* a span of milliseconds in words: "45 s", "6 min", "5 min 12 s", "3 h" */
export function span(ms, seconds = false) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m >= 120) return `${Math.floor(m / 60)} h`;
  return seconds && s % 60 ? `${m} min ${s % 60} s` : `${m} min`;
}
const since = (iso, now) => span(now - new Date(iso).getTime());

function productOf(ctx, productId) {
  const p = (productId && ctx.products.find((x) => x.id === productId)) || ctx.product;
  if (!p) throw new Error("This org has no products yet.");
  return { id: p.id, key: p.key, name: p.name };
}

const testersOf = (members) => members.filter((m) => !m.removed_at && RUNS.includes(m.role)).map((m) => ({ handle: m.actor_id, name: m.name || m.email, role: m.role }));

/* a plan's line on step 1: "3 features · 1 query · 28 cases", "any version · 18 cases", "draft · scoped to 2.15.0" */
function planMeta(p, ver) {
  const v = p.release_id ? ver[p.release_id] : "";
  if (p.status === "draft") return v ? `draft · scoped to ${v}` : "draft";
  if (p.status === "archived") return v ? `archived · ${v}` : "archived";
  const nf = p.entries.filter((e) => e.feature_id).length, nq = p.entries.filter((e) => e.query).length;
  const n = p.entries.reduce((a, e) => a + (e.new_cases || 0), 0);
  return [v ? "" : "any version", nf ? plural(nf, "feature") : "", nq ? plural(nq, "query", "queries") : "", plural(n, "case")].filter(Boolean).join(" · ");
}

/* each machine as a pick: busy ones say when they're free, from their current job's cycle ETA (F8). chosen is
   the ?machines= ids, or null for "every machine that can run now". */
async function machines(at, consumers, product, keys, now, chosen) {
  const busy = consumers.filter((c) => c.status === "busy" && c.busy_job_id);
  const etas = Object.fromEntries(await Promise.all(busy.map(async (c) => {
    const jobs = await page(at("consumers", c.id, "jobs"), { limit: 20 });
    const job = jobs.items.find((j) => j.id === c.busy_job_id);
    const cycle = job ? await get(at("cycles", job.cycle_id)) : null;
    return [c.id, cycle && cycle.eta ? new Date(cycle.eta).getTime() : null];
  })));
  return consumers.map((c) => {
    const allowed = c.product_ids.includes(product.id) && !c.paused_at;
    const sys = [c.os, c.tj_version ? `tj ${c.tj_version}` : ""].filter(Boolean).join(" · ");
    const eta = etas[c.id];
    const meta = !c.product_ids.includes(product.id) ? `Not allowed for ${product.key}: paired for ${c.product_ids.map((id) => keys[id]).filter(Boolean).join(", ") || "no product"} only`
      : c.paused_at ? `Paused ${since(c.paused_at, now)} ago`
      : c.status === "offline" ? (c.last_heartbeat_at ? `Last heartbeat ${since(c.last_heartbeat_at, now)} ago` : "No heartbeat yet")
      : c.status === "busy" ? `${sys} · queues after its current job${eta && eta > now ? ` (about ${span(eta - now)})` : ""}`
      : `${sys} · idle`;
    const can = allowed && c.status !== "offline";
    return { id: c.id, name: c.name, status: c.status, meta, on: can && (!chosen || chosen.includes(c.id)), can, allowed, heartbeat: c.last_heartbeat_at };
  });
}

async function wizard(at, ctx, params, ui) {
  const product = productOf(ctx, null);
  const now = Date.now();
  const [releases, plans, tree, members, consumers, cycles] = await Promise.all([
    all(at("products", product.key, "releases")),
    all(at("products", product.key, "plans"), { include_archived: true }),
    get(at("products", product.key, "features")),
    all(at("members")),
    all(at("consumers")),
    all(at("products", product.key, "cycles"))
  ]);
  const ver = Object.fromEntries(releases.map((r) => [r.id, r.version]));
  const keys = Object.fromEntries(ctx.products.map((p) => [p.id, p.key]));
  const picked = params.plan ? plans.find((p) => p.id === params.plan) : null;
  const release = releases.find((r) => r.id === params.version) || (picked && releases.find((r) => r.id === picked.release_id)) || releases.find((r) => ctx.version && r.id === ctx.version.id) || releases[0] || null;
  const byFeatures = ui === "scope-features" || (!!params.features && !params.plan);
  const featureIds = params.features ? params.features.split(",").filter(Boolean) : (release ? release.feature_ids : []);
  const plan = byFeatures ? null : picked || plans.find((p) => p.status === "active" && (!p.release_id || !release || p.release_id === release.id)) || null;
  const features = flatten(tree.items).map((f) => ({ id: f.id, path: f.path, cases: f.total_case_count, on: featureIds.includes(f.id) }));
  const chosen = params.machines ? params.machines.split(",").filter(Boolean) : null;
  const mach = await machines(at, consumers.filter((c) => c.status !== "revoked"), product, keys, now, chosen);
  const ready = mach.filter((m) => m.on);
  /* what the run would pin, per runner: machines that can run now take what their inventory lists */
  const source = plan ? { plan_id: plan.id } : byFeatures && featureIds.length ? { feature_ids: featureIds } : null;
  const preview = source ? await post(at("products", product.key, "cycles", "preview"), ready.length ? { ...source, mode: "both", consumer_ids: ready.map((m) => m.id) } : { ...source, mode: "manual" }) : null;
  const automated = preview ? preview.runners.consumers.reduce((n, c) => n + c.cases, 0) : 0;
  const name = plan ? plan.name : plural(features.filter((f) => f.on).length, "feature");
  const envs = [...new Set([...cycles].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)).map((c) => c.environment).filter(Boolean))];
  const environment = params.env || envs[0] || "";
  const testers = testersOf(members);
  const tester = testers.find((t) => t.role === "tester") || testers[0];
  const newest = mach.some((m) => m.can) ? null : mach.filter((m) => m.allowed && m.heartbeat).map((m) => new Date(m.heartbeat).getTime()).sort((a, b) => b - a)[0];
  const order = ORDER[params.order] ? params.order : "feature";
  const data = {
    /* the picks so far, carried in the URL from step to step */
    query: {
      version: release ? release.id : null, plan: plan ? plan.id : null, features: byFeatures ? featureIds.join(",") : null,
      env: params.env || null, name: params.name || null, tester: params.tester || null, order: params.order || null, machines: params.machines || null
    },
    order,
    /* the machines' defaults: whole features per machine, a failed case retried once (the v4 mock) */
    split: "by_feature", retries: 1,
    product, version: release ? release.version : "any version", versionId: release ? release.id : null,
    products: ctx.products.map((p) => ({ key: p.key, name: p.name, markCls: p.markCls })),
    versions: releases.map((r) => ({ id: r.id, ver: r.version, hint: r.status.replace("_", " ") + (r.feature_ids.length ? ` · ${plural(r.feature_ids.length, "feature")}` : "") })),
    plan: { id: plan ? plan.id : null, name, cases: preview ? preview.total : 0, automated, manual: preview ? preview.runners.person : 0 },
    plans: plans.map((p) => ({ id: p.id, name: p.name, meta: planMeta(p, ver), on: !!plan && p.id === plan.id, cantRun: p.status !== "active" })),
    features, featureIds: features.filter((f) => f.on).map((f) => f.id),
    environments: envs.length ? envs : environment ? [environment] : [], environment,
    cycleName: params.name || (environment ? `${name} · ${environment}` : name),
    testers, tester: params.tester || (tester ? tester.handle : "none"), mixedTesters: testers.map((t) => t.handle),
    machines: mach,
    heartbeatWindow: newest ? span(now - newest) : "",
    /* the live cycle's shape, unused by the wizard */
    cycle: null
  };
  const auto = ui === "auto-pick" || ui === "mixed-pick";
  if (auto && !ready.length && ui === "auto-pick") return { state: "auto-none", data };
  return { state: WIZARD.includes(ui) ? ui : byFeatures ? "scope-features" : "scope", data };
}

async function live(at, ctx, params) {
  const c = await get(at("cycles", params.id));
  const product = productOf(ctx, c.product_id);
  const now = Date.now();
  const [jobs, cases, consumers, members, release] = await Promise.all([
    all(at("cycles", c.id, "jobs")),
    all(at("cycles", c.id, "cases"), { sort: "position" }),
    all(at("consumers")),
    all(at("members")),
    c.release_id ? get(at("releases", c.release_id)) : null
  ]);
  const by = Object.fromEntries(consumers.map((x) => [x.id, x]));
  const name = (id) => (by[id] || {}).name || id || "";
  const auto = cases.filter((x) => x.runner === "consumer"), manual = cases.filter((x) => x.runner !== "consumer");
  const ran = auto.filter((x) => x.status !== "untested");
  const passed = auto.filter((x) => x.status === "success").length;
  const failedRows = auto.filter((x) => x.status === "fail" || x.status === "error");
  const finished = c.status === "closed" || (jobs.length > 0 && jobs.every((j) => DONE_JOB.includes(j.status)));
  const ends = jobs.map((j) => j.finished_at).filter(Boolean).sort();
  const end = finished && ends.length ? new Date(ends[ends.length - 1]).getTime() : now;
  const eta = c.eta ? new Date(c.eta).getTime() : null;
  const jobRows = jobs.map((j) => {
    const mine = auto.filter((x) => x.consumer_id === j.consumer_id);
    return { id: j.id, consumerId: j.consumer_id, status: j.status, machine: name(j.consumer_id), features: j.project, done: mine.filter((x) => x.status !== "untested").length, total: mine.length || 1 };
  });
  /* a held or queued job whose machine went offline is stalled: its untested cases wait */
  const stuck = jobRows.find((j) => !DONE_JOB.includes(j.status) && (by[j.consumerId] || {}).status === "offline");
  const spare = stuck && consumers.find((x) => x.id !== stuck.consumerId && x.status !== "offline" && !x.paused_at && x.product_ids.includes(product.id));
  const stalled = stuck ? {
    machine: stuck.machine, jobId: stuck.id, since: by[stuck.consumerId].last_heartbeat_at ? since(by[stuck.consumerId].last_heartbeat_at, now) : "a while",
    waiting: stuck.total - stuck.done, reassignTo: spare ? spare.name : "", reassignId: spare ? spare.id : null
  } : null;
  const testers = testersOf(members);
  const data = {
    product, version: release ? release.version : "", releaseId: c.release_id,
    testers, plan: { id: c.plan_id },
    cycle: {
      id: c.id, name: c.name, mode: c.mode === "both" ? "mixed" : "auto", finished, queued: jobs.length > 0 && jobs.every((j) => j.status === "queued"),
      counts: results(c.counts), done: ran.length, total: auto.length, passed, passedPct: ran.length ? Math.round((passed / ran.length) * 100) : 0,
      failed: failedRows.length, failedKeys: failedRows.map((x) => x.key), elapsed: span(end - new Date(c.started_at).getTime(), true),
      left: eta && eta > now && !finished ? span(eta - now) : "",
      jobs: jobRows,
      results: auto.slice(0, 12).map((x) => ({ id: x.id, key: x.key, title: x.title, machine: name(x.consumer_id), status: x.status, time: "" })),
      manual: { count: manual.length, done: manual.filter((x) => x.status !== "untested").length, cases: manual.slice(0, 2).map((x) => ({ key: x.key, title: x.title })) },
      manualTester: c.default_assignee_actor_id || "",
      stalled,
      /* cycles_stop: queued jobs cancelled, running ones finish */
      stopped: !!c.stopped_at, stoppedBy: c.stopped_by_actor_id ? ((members.find((x) => x.actor_id === c.stopped_by_actor_id) || {}).name || "") : ""
    },
    moved: params.moved ? { count: Number(params.moved), to: params.to || "" } : null
  };
  const mixed = c.mode === "both";
  if (params.ui === "reassigned" && data.moved) return { state: "reassigned", data };
  if (stalled) return { state: params.ui === "cancel-cases" ? "cancel-cases" : "offline-mid", data };
  if (finished) return { state: mixed ? "done-mixed" : "done", data };
  if (data.cycle.queued) return { state: "queued", data };
  return { state: mixed ? "mixed" : "live", data };
}

/* params: the URL's query (id: a started cycle; else plan, features, version, env, name, tester for the wizard)
   and ui, the hash's step ("mode", "manual-ready", "auto-pick", ...). */
export async function load(params, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  if (params.id) return live(at, ctx, params);
  return wizard(at, ctx, params, params.ui);
}

const at = (ctx) => (...rest) => org(ctx.org.id, ...rest);
/* the Order menu's values, as cycles_create's order */
const ORDER = { feature: "feature", priority: "priority", plan: "source" };
/* cycles_create's split strategies */
const SPLITS = ["even", "by_feature", "first_free"];

/* The view's writes; each resolves to the server's object (CycleOut or JobOut). */
export const actions = {
  /* form: { plan (id) | features ([id]), name, environment, mode ("manual", "auto", "mixed"), tester (actor id or
     "none"), order ("feature", "priority", "plan"), machines ([consumer id]), release (id), and for machines split
     ("even", "by_feature", "first_free"), retries (0-2), offline (queue on offline machines) } */
  start(form, ctx, productKey) {
    const mode = MODES[form.mode] || "manual";
    const auto = mode !== "manual";
    return post(at(ctx)("products", productKey, "cycles"), {
      ...(form.plan ? { plan_id: form.plan } : { feature_ids: form.features || [] }),
      name: form.name, environment: form.environment || null, mode,
      consumer_ids: auto ? form.machines : undefined,
      default_assignee_actor_id: form.tester && form.tester !== "none" ? form.tester : null,
      order: ORDER[form.order] || "source",
      release_id: form.plan ? undefined : form.release || undefined,
      split: auto && SPLITS.includes(form.split) ? form.split : undefined,
      retries: auto && form.retries !== undefined && form.retries !== "" ? Number(form.retries) : undefined,
      queue_when_offline: auto ? !!form.offline : undefined
    });
  },
  reassign: (jobId, consumerId, ctx) => post(at(ctx)("jobs", jobId, "reassign"), { consumer_id: consumerId }),
  cancel: (jobId, ctx) => post(at(ctx)("jobs", jobId, "cancel")),
  stop: (cycleId, ctx) => post(at(ctx)("cycles", cycleId, "stop"))
};
