/* MCP server adapter (docs/app-api-contract.md §15): mcp_server_get, mcp_tools_list, mcp_usage, mcp_clients,
   mcp_updates and mcp_calls for the chosen range, and the OpenAPI document for the API's operation count and a
   tool's operation (path and args). Maps them onto the shapes views/mcp.js renders. The range runs in the
   browser's zone: hour buckets are grouped into local hours or days. poll() is the live mode's 15 s refresh. */
import { get, org, page } from "../api.js";

const OPENAPI = "/api/v1/openapi.json";
const API_PREFIX = "/api/v1/";
const METHODS = ["get", "post", "put", "patch", "delete"];
/* the request headers a tool takes as args (mcp_server/generator.py HEADER_ARGS) */
const HEADER_ARGS = { "If-Match": "expected_version", "Idempotency-Key": "idempotency_key" };
const DAYS = { "7d": 7, "14d": 14, "30d": 30 };
const LIVE = ["today", "7d", "14d", "30d", "tool-detail", "empty"];
const HOUR = 3600e3;

/* ---- time, in the browser's zone ---- */
const sp = (s) => s.replace(/[  ]/g, " ");
const midnight = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const clock = (d) => sp(d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }));
const md = (d) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
const wd = (d) => d.toLocaleDateString("en-US", { weekday: "short" });
const zone = (d = new Date()) => (new Intl.DateTimeFormat("en-US", { timeZoneName: "short" }).formatToParts(d).find((p) => p.type === "timeZoneName") || {}).value || "";
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
/* "2026-11-02" (or "2026-11-2") as that local day's midnight */
function parseDay(s) {
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(String(s || ""));
  if (!m) throw new Error(`Not a date: ${s}`);
  return new Date(+m[1], +m[2] - 1, +m[3]);
}
/* "Sat Nov 14, 9:12 AM PST" */
const stamp = (d) => `${wd(d)} ${md(d)}, ${clock(d)} ${zone(d)}`;
/* a call's time in a list: "3:14 PM" today, else "Fri 4:20 PM" (with the date past a week) */
function short(d, now = new Date()) {
  if (+midnight(d) === +midnight(now)) return clock(d);
  return now - d < 6 * 864e5 ? `${wd(d)} ${clock(d)}` : `${md(d)}, ${clock(d)}`;
}
/* the live "last call" time: "just now", "4 min ago", else as in a list */
function ago(d, now = new Date()) {
  const s = (now - d) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return short(d, now);
}

/* ---- the range: its columns and the [since, until) it asks for ---- */
const hourX = (h) => (h % 3 ? "" : `${h % 12 || 12}${h < 12 ? "a" : "p"}`);
const every = (n) => (n <= 8 ? 1 : n <= 16 ? 2 : n <= 35 ? 5 : 10);
function windowOf(range, picker, now) {
  const today = midnight(now);
  if (range === "today") {
    const end = addDays(today, 1), cols = [];
    for (let t = today; t < end; t = new Date(+t + HOUR)) {
      const b = new Date(+t + HOUR);
      cols.push({ a: t, b, x: hourX(t.getHours()), tip: `${wd(t)} ${md(t)} · ${clock(t)}–${clock(b)} ${zone(t)}`, later: t > now });
    }
    return { since: today, until: end, cols, live: true };
  }
  const start = range === "custom" ? parseDay(picker.from) : addDays(today, 1 - DAYS[range]);
  const end = range === "custom" ? addDays(parseDay(picker.to), 1) : addDays(today, 1);
  const cols = [];
  for (let t = start, i = 0; t < end; t = addDays(t, 1), i++) cols.push({ a: t, b: addDays(t, 1), i });
  const k = every(cols.length);
  for (const c of cols) {
    c.x = c.i % k ? "" : range === "7d" ? `${wd(c.a)} ${c.a.getDate()}` : md(c.a);
    c.tip = range === "7d" ? `${wd(c.a)} ${md(c.a)}` : md(c.a);
  }
  return { since: start, until: end, cols, live: range !== "custom" };
}
const span = (w) => ({ since: w.since.toISOString(), until: w.until.toISOString() });

/* hour buckets into the window's columns: reads, writes and errors per column */
function columns(w, buckets, now) {
  const out = w.cols.map((c) => (c.later ? { x: c.x, later: true } : { x: c.x, tip: c.tip, reads: 0, writes: 0, errors: 0 }));
  for (const b of buckets) {
    const t = new Date(b.start);
    const i = w.cols.findIndex((c) => c.a <= t && t < c.b);
    if (i < 0 || out[i].later) continue;
    out[i].reads += b.reads;
    out[i].writes += b.writes;
    out[i].errors += b.errors;
  }
  const at = w.live ? w.cols.findIndex((c) => c.a <= now && now < c.b) : -1;
  return { columns: out, now: at };
}
const sum = (xs, f) => xs.reduce((n, x) => n + f(x), 0);

/* ---- tools ---- */
const kindOf = (t) => (t.destructive ? "d" : t.read_only ? "r" : t.idempotent ? "i" : "w");
const tool = (t, range) => ({
  name: t.name, toolset: t.toolset, scope: t.scope || "", desc: t.description, kind: kindOf(t),
  tokCall: t.p50_resp_tokens, tokDef: t.def_tokens, calls: { [range]: t.calls }, errors: t.errors, p95: t.p95_resp_tokens
});
/* the API's operations in the OpenAPI document, in its order */
const operations = (spec) => Object.entries(spec.paths || {}).filter(([p]) => p.startsWith(API_PREFIX))
  .flatMap(([path, item]) => METHODS.filter((m) => item[m]).map((m) => ({ path, method: m, o: item[m] })));
/* toolsets in the order the API declares them, admin last */
function toolsets(ops, tools) {
  const seen = [];
  for (const { o } of ops) if (o["x-mcp"] && o["x-toolset"] && !seen.includes(o["x-toolset"])) seen.push(o["x-toolset"]);
  for (const t of tools) if (!seen.includes(t.toolset)) seen.push(t.toolset);
  return seen.filter((t) => t !== "admin").concat(seen.includes("admin") ? ["admin"] : []);
}
/* the most frequent error status over the tools, or null (calls recorded before F6 carry no status) */
function mostly(items) {
  const by = {};
  for (const t of items) for (const [code, n] of Object.entries(t.errors_by_code || {})) by[code] = (by[code] || 0) + n;
  const top = Object.entries(by).sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))[0];
  return top ? top[0] : null;
}

/* a schema's type in words: a $ref's name, "string[]", "integer | string" */
function typeOf(s) {
  if (!s) return "any";
  if (s.$ref) return s.$ref.split("/").pop();
  const alt = s.anyOf || s.oneOf;
  if (alt) return alt.filter((x) => x.type !== "null").map(typeOf).join(" | ") || "null";
  if (s.type === "array") return `${typeOf(s.items)}[]`;
  return s.type || "any";
}
const resolve = (s, spec) => (s && s.$ref ? spec.components.schemas[s.$ref.split("/").pop()] : s);
/* the tool's args, as the MCP generator builds them from its operation: path and query params, the mapped
   headers, then the JSON body's fields */
function args(op, spec) {
  const out = [];
  for (const p of op.o.parameters || []) {
    if (p.in === "path" || p.in === "query") out.push({ arg: p.name, where: p.in, type: typeOf(p.schema), required: !!p.required, note: p.description || "" });
    else if (p.in === "header" && HEADER_ARGS[p.name]) out.push({ arg: HEADER_ARGS[p.name], where: `header ${p.name}`, type: HEADER_ARGS[p.name] === "expected_version" ? "integer" : typeOf(p.schema), required: !!p.required, note: p.description || "" });
  }
  const body = op.o.requestBody;
  const schema = body && body.content && body.content["application/json"] && resolve(body.content["application/json"].schema, spec);
  if (schema && schema.properties) {
    const req = body.required ? schema.required || [] : [];
    for (const [name, f] of Object.entries(schema.properties)) out.push({ arg: name, where: "body", type: typeOf(f), required: req.includes(name), note: f.description || "" });
  }
  return out;
}

const call = (c, now, live) => ({
  call: c.tool, agent: c.name, kind: c.kind, actorId: c.actor_id, code: c.status, ms: c.ms, tokens: c.resp_tokens,
  at: live ? ago(new Date(c.at), now) : short(new Date(c.at), now)
});

async function screen(at, range, picker, now) {
  const w = windowOf(range, picker, now);
  const q = span(w);
  const [server, toolsOut, usage, clients, updates, last, spec] = await Promise.all([
    get(at("mcp", "server")),
    get(at("mcp", "tools"), q),
    get(at("mcp", "usage"), { ...q, bucket: "hour" }),
    get(at("mcp", "clients"), q),
    page(at("mcp", "updates"), { limit: 5 }),
    page(at("mcp", "calls"), w.live ? { limit: 1 } : { ...q, limit: 1 }),
    get(OPENAPI)
  ]);
  const ops = operations(spec);
  const tools = toolsOut.items.map((t) => tool(t, range));
  const { columns: cols, now: nowAt } = columns(w, usage.items, now);
  const c = last.items[0];
  const data = {
    range, picker, loading: false, zone: zone(now),
    server: { up: true, version: server.version },
    apiOps: ops.length,
    toolsets: toolsets(ops, tools),
    tools,
    ranges: { [range]: { now: nowAt, columns: cols, totals: {
      calls: sum(usage.items, (b) => b.calls), errors: sum(usage.items, (b) => b.errors),
      tokens: Math.round(sum(usage.items, (b) => b.resp_bytes) / 4), clients: clients.items.length
    } } },
    errorsMostly: mostly(toolsOut.items),
    clientNames: clients.items.map((x) => x.name),
    lastCall: c ? call(c, now, w.live) : null,
    connect: { base: String(globalThis.location?.origin || "") },
    updates: updates.items.map(update),
    live: null
  };
  if (w.live) {
    const col = w.cols[nowAt];
    data.live = { since: q.since, until: q.until, nowStart: col.a.toISOString(), nowEnd: col.b.toISOString() };
  }
  return { data, ops, spec };
}

/* one row of the updates feed */
function update(u) {
  const at = stamp(new Date(u.at));
  if (u.kind === "server_started") return { kind: "acc", icon: "spark", title: `Server v${u.version} started`, text: "", at };
  const list = [...u.added.map((n) => "+" + n), ...u.removed.map((n) => "−" + n)].join(", ");
  const changed = u.changed.length ? `Schema changed: ${u.changed.join(", ")}` : "";
  if (!list) return { kind: "info", icon: "build", title: changed || `Server v${u.version} started`, text: `v${u.version}`, at };
  return { kind: "info", icon: "plus", title: `Tool list changed: ${list}`, text: changed || `v${u.version}`, at };
}

/* params: the URL's query (id: a tool name; from, to: a custom range) and ui, the hash's range or UI state. */
export async function load(params, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  const ui = params.ui || "";
  const now = new Date();
  if (params.id) {
    const { data, ops, spec } = await screen(at, "today", null, now);
    const t = data.tools.find((x) => x.name === params.id);
    if (!t) throw new Error(`No MCP tool is named ${params.id}.`);
    const op = ops.find((x) => x.o.operationId === t.name);
    const calls = await page(at("mcp", "calls"), { tool: t.name, limit: 5 });
    data.detail = {
      tool: t.name, path: op ? op.path : "", errorsToday: t.errors, p95: t.p95,
      params: op ? args(op, spec) : [], calls: calls.items.map((c) => call(c, now, false)), audited: t.kind !== "r"
    };
    return { state: "tool-detail", data };
  }
  let range = "today", state = "today", picker = null;
  if (DAYS[ui]) range = state = ui;
  else if (ui === "today-hover") state = ui;
  else if (ui === "custom-open") { range = "7d"; state = ui; picker = { value: "custom", open: true }; }
  else if (ui === "custom-applied" && params.from && params.to) {
    range = "custom"; state = ui;
    picker = { value: "custom", applied: true, from: iso(parseDay(params.from)), to: iso(parseDay(params.to)) };
  }
  const { data } = await screen(at, range, picker, now);
  if (range === "today" && data.ranges.today.totals.calls === 0) state = "empty";
  if (!LIVE.includes(state)) data.live = null;
  return { state, data };
}

/* Live mode, every 15 s (contract §15 "Live": mcp_usage, mcp_clients, mcp_calls?limit=1): the range's calls
   so far, the current column's reads, writes and errors, the clients and the latest call. live is data.live
   from load. */
export async function poll(live, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  const now = new Date();
  const q = { since: live.since, until: live.until };
  const [usage, clients, last] = await Promise.all([
    get(at("mcp", "usage"), { ...q, bucket: "hour" }),
    get(at("mcp", "clients"), q),
    page(at("mcp", "calls"), { limit: 1 })
  ]);
  const a = new Date(live.nowStart), b = new Date(live.nowEnd);
  const cur = usage.items.filter((x) => { const t = new Date(x.start); return a <= t && t < b; });
  return {
    calls: sum(usage.items, (x) => x.calls),
    clients: clients.items.map((x) => x.name),
    now: { reads: sum(cur, (x) => x.reads), writes: sum(cur, (x) => x.writes), errors: sum(cur, (x) => x.errors) },
    lastCall: last.items[0] ? call(last.items[0], now, true) : null
  };
}

/* The view makes no writes. */
export const actions = {};
