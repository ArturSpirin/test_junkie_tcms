/* Consumers (machines) adapter (docs/app-api-contract.md §16): consumers_list (status and q are the server's),
   consumers_get, consumers_jobs and consumers_roster for one machine, cycles_get for its jobs' names,
   pairings_get, pairings_approve and pairings_deny for pairing, and consumers_update, consumers_pause,
   consumers_resume and consumers_revoke. Maps the API onto the shapes views/consumers.js renders. */
import { all, del, get, org, page, patch, post } from "../api.js";

const STATUSES = ["online", "busy", "offline"];
/* a pairing user code is 8 letters, shown XXXX-XXXX (RFC 8628 device flow) */
const CODE_LENGTH = 8;
const DETAIL_UI = ["rename", "revoke-confirm", "detail-hover"];
const HOUR = 3600e3;

const plural = (n, one) => `${n} ${n === 1 ? one : one + "s"}`;
/* "4 s ago", "12 min ago", "3 h ago", "2 d ago" */
function ago(iso, now) {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((now - new Date(iso)) / 1000));
  if (s < 60) return `${s} s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h} h ago` : `${Math.floor(h / 24)} d ago`;
}
/* a length of time: "3 h 12 min", "8 min 42 s" */
function span(ms, seconds = false) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60), h = Math.floor(m / 60);
  if (h) return `${h} h ${m % 60} min`;
  return seconds ? `${m} min ${s % 60} s` : `${m} min`;
}
const clock = (iso) => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
const zone = () => (new Intl.DateTimeFormat("en-US", { timeZoneName: "short" }).formatToParts(new Date()).find((x) => x.type === "timeZoneName") || {}).value || "";
/* product ids as the keys people know them by */
const keys = (ctx, ids) => ids.map((id) => (ctx.products.find((p) => p.id === id) || { key: id }).key);
const ids = (ctx, ks) => ks.map((k) => (ctx.products.find((p) => p.key === k) || { id: k }).id);

const card = (ctx, c, now) => ({
  id: c.id, name: c.name, status: c.status, paused: !!c.paused_at, heartbeat: ago(c.last_heartbeat_at, now),
  os: c.os || "", tj: c.tj_version || "", python: c.python || "", products: keys(ctx, c.product_ids), projects: c.project_count
});

/* the first n items of a paged list, newest first (n may pass one page) */
async function first(path, query, n) {
  const out = [];
  let cursor = null;
  while (out.length < n) {
    const p = await page(path, { ...query, limit: Math.min(200, n - out.length), cursor });
    out.push(...p.items);
    if (!(cursor = p.next)) break;
  }
  return out;
}

async function list(at, ctx, params, now) {
  const q = (params.q || "").trim();
  const status = STATUSES.includes(params.status) ? params.status : "";
  const [hits, every, ...by] = await Promise.all([
    page(at("consumers"), { q, status, limit: 200 }),
    page(at("consumers"), { limit: 1 }),
    ...STATUSES.map((s) => page(at("consumers"), { status: s, limit: 1 }))
  ]);
  const counts = { all: every.total, ...Object.fromEntries(STATUSES.map((s, i) => [s, by[i].total])) };
  const data = { q, filter: status || "all", counts, machines: hits.items.map((c) => card(ctx, c, now)), pair: null, paired: null };
  if (params.paired) {
    data.paired = card(ctx, await get(at("consumers", params.paired)), now);
    return { state: "paired", data };
  }
  if (q) return { state: hits.total ? "search" : "search-empty", data };
  if (status) return { state: `filter-${status}`, data };
  return { state: counts.all ? "list" : "empty", data };
}

/* the pairing steps: #pair is the code entry; ?code= is the request the machine made, named and approved here */
async function pairing(at, ctx, params, now) {
  const code = (params.code || "").replace(/[^a-z0-9]/gi, "").toUpperCase().slice(0, CODE_LENGTH);
  const origin = globalThis.location && globalThis.location.origin;
  const data = {};
  data.pair = {
    code, server: origin || "", codeLength: CODE_LENGTH, ttlMin: null, typed: code, expiresIn: "", name: "",
    os: "", tj: "", python: "", projects: [], products: ctx.product ? [ctx.product.key] : [], acceptNow: true
  };
  if (params.ui === "pair" || !code) return { state: "pair", data };
  const p = await get(at("pair", code));
  Object.assign(data.pair, {
    expiresIn: span(new Date(p.expires_at) - now, true), os: p.os || "", tj: p.tj_version || "", python: p.python || "", projects: p.projects || []
  });
  return { state: params.ui === "pair-noname" ? "pair-noname" : "pair-approve", data };
}

/* heartbeats and jobs per hour, the last 24 hours, the current hour last */
function beats(heartbeats, jobs, now) {
  const top = new Date(now);
  top.setMinutes(0, 0, 0);
  const start = top.getTime() - 23 * HOUR;
  const bucket = (iso) => Math.floor((new Date(iso).getTime() - start) / HOUR);
  const count = (rows, at) => {
    const n = Array(24).fill(0);
    for (const r of rows) { const i = bucket(at(r)); if (i >= 0 && i < 24) n[i] += 1; }
    return n;
  };
  return { expected: null, startHour: new Date(start).getHours(), tz: zone(), beats: count(heartbeats, (b) => b.at), jobs: count(jobs, (j) => j.created_at) };
}

async function detail(at, ctx, params, now) {
  const id = params.id;
  const c = await get(at("consumers", id));
  const jobs = at("consumers", id, "jobs");
  const roster = at("consumers", id, "roster");
  const [held, running, queued, rejected, recent, tests] = await Promise.all([
    all(jobs, { status: "claimed" }), all(jobs, { status: "running" }), all(jobs, { status: "queued" }),
    first(jobs, { status: "rejected" }, c.rejected_today),
    first(jobs, {}, c.jobs_today),
    params.tests === "all" ? all(roster) : page(roster, { limit: 50 }).then((p) => p.items)
  ]);
  const shown = [...running, ...held, ...queued, ...rejected];
  const cycles = Object.fromEntries(await Promise.all([...new Set(shown.map((j) => j.cycle_id))].map(async (cid) => [cid, await get(at("cycles", cid))])));
  const job = (j) => {
    const cy = cycles[j.cycle_id];
    return {
      id: j.id, cycleId: j.cycle_id, name: cy.name, state: j.status, project: j.project, reason: j.reason || "",
      detail: [cy.environment, plural(j.refs.length, "test"), `timeout ${Math.round(j.timeout_s / 60)} min`].filter(Boolean).join(" · "),
      done: null, total: j.refs.length
    };
  };
  const updated = c.inventory.map((i) => i.updated_at).sort().pop();
  const machine = {
    id: c.id, name: c.name, status: c.status, paused: !!c.paused_at, heartbeat: ago(c.last_heartbeat_at, now),
    silentFor: c.last_heartbeat_at ? span(now - new Date(c.last_heartbeat_at)) : "",
    lastHeartbeat: c.last_heartbeat_at ? clock(c.last_heartbeat_at) : "",
    jobsToday: c.jobs_today, rejectedToday: c.rejected_today, testsFound: c.tests_found, testsLinked: c.tests_linked,
    tj: c.tj_version || "", python: c.python || "", os: c.os || "", products: keys(ctx, c.product_ids),
    projects: c.inventory.map((i) => ({ name: i.project, products: [] })),
    jobs: shown.map(job), rejectError: rejected.length ? rejected[0].reason || "" : "",
    hb: beats(c.heartbeats, recent, now), rescanned: ago(updated, now),
    tests: tests.map((t) => ({ ref: t.ref, caseKey: t.case_key || null })), allTests: params.tests === "all"
  };
  const data = { machine, renameTo: c.name, hoverCol: 23 };
  if (DETAIL_UI.includes(params.ui)) return { state: params.ui, data };
  if (c.status === "offline") return { state: "offline", data };
  return { state: rejected.length ? "job-rejected" : "detail", data };
}

/* params: the URL's query (id, q, status, code, paired, tests) and ui, the hash's UI state ("pair", "rename", ...). */
export async function load(params, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  const now = Date.now();
  if (params.id) return detail(at, ctx, params, now);
  if (params.code || params.ui === "pair" || params.ui === "pair-approve" || params.ui === "pair-noname") return pairing(at, ctx, params, now);
  return list(at, ctx, params, now);
}

const at = (ctx) => (...rest) => org(ctx.org.id, ...rest);

/* The view's writes; each resolves to what the server returns (ConsumerOut, or null for a 204). */
export const actions = {
  /* form: { code, name, products (product keys), acceptNow } */
  approve: (form, ctx) => post(at(ctx)("pair", "approve"), {
    user_code: form.code, name: form.name, product_ids: ids(ctx, form.products), accept_jobs: !!form.acceptNow
  }),
  deny: (code, ctx) => post(at(ctx)("pair", "deny"), { user_code: code }),
  rename: (id, name, ctx) => patch(at(ctx)("consumers", id), { name }),
  pause: (id, ctx) => post(at(ctx)("consumers", id, "pause")),
  resume: (id, ctx) => post(at(ctx)("consumers", id, "resume")),
  revoke: (id, ctx) => del(at(ctx)("consumers", id))
};
