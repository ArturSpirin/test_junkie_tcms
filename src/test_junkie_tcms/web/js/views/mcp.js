/* MCP server: usage by date range, the tool list, connection details, updates and one tool's detail drawer. */
import { I, actor, dd, dr, tg, toast, esc, tipA, pinTip, crumbs, lnk, person } from "../ui.js";

const K = (n) => n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M" : n >= 1000 ? (n / 1000).toFixed(n >= 1e4 ? 0 : 1).replace(/\.0$/, "") + "k" : String(n);
const N = (n) => n.toLocaleString("en-US");
const k1 = (n) => (n / 1000).toFixed(1) + "k";
const ANN = { r: ["r", "read-only"], i: ["i", "idempotent"], d: ["d", "destructive"], w: ["", "write"] };
const ann = (k) => `<span class="ann ${ANN[k][0]}">${ANN[k][1]}</span>`;
/* ranges: what one chart column covers, and whether the range runs up to now (live) */
const RANGE = { today: { unit: "per hour", live: true }, "7d": { unit: "per day", live: true }, "14d": { unit: "per day", live: true }, "30d": { unit: "per day", live: true }, custom: { unit: "per day", live: false } };
const ymd = (s) => { const [y, m, day] = s.split("-").map(Number); return new Date(y, m - 1, day); };
const defTools = (d) => d.tools.filter((t) => t.toolset !== "admin");
const ctxTokens = (ts) => K(ts.reduce((n, t) => n + t.tokDef, 0));
const callMeta = (c) => `${c.ms} ms · ≈ ${k1(c.tokens)} tokens`;

function chart(d, r, dim) {
  const R = d.ranges[r];
  const max = Math.max(...R.columns.filter((c) => !c.later).map((c) => c.reads + c.writes + c.errors)) * 1.12;
  const pct = (v) => (v / max * 100).toFixed(2) + "%";
  const cols = R.columns.map((c, i) => !c.later ? `<div class="col${i === R.now ? " now" : ""}" data-a="${c.reads}"${tipA(c.tip + (r === "today" && i === R.now ? " · now" : ""), [["reads", "var(--accent)", c.reads], ["writes", "var(--retest)", c.writes], ["errors", "var(--st-error)", c.errors]], ["Total calls", c.reads + c.writes + c.errors])}>${c.reads ? `<i class="a" style="height:${pct(c.reads)}"></i>` : ""}${c.writes ? `<i class="b" style="height:${pct(c.writes)}"></i>` : ""}${c.errors ? `<i class="c" style="height:${pct(c.errors)}"></i>` : ""}</div>` : `<div class="col"${tipA("Later today", [["no data yet", "var(--st-untested)", "–"]])}><i class="z" style="height:2px"></i></div>`).join("");
  const gl = [.25, .5, .75, 1].map((f) => `<span class="gl" style="bottom:${f * 100}%"><em>${K(Math.round(max * f))}</em></span>`).join("");
  return `<div class="chart-wrap"><div class="chart${dim ? " dim" : ""}" data-max="${max}" style="margin-top:14px">${gl}${cols}</div><div class="chart-x">${R.columns.map((c) => `<span>${esc(c.x)}</span>`).join("")}</div></div>`;
}

/* ---- pieces ---- */
const legend3 = `<div class="legend"><span style="--c:var(--accent)">reads</span><span style="--c:var(--retest)">writes</span><span style="--c:var(--st-error)">errors</span></div>`;
function head(d, o) {
  const stat = o.off ? `<span class="hstat off"><span class="live"></span>Unreachable</span>` : `<span class="hstat"><span class="live"></span>Serving · v${esc(d.server.version)} · ${esc(d.server.transports)}</span>`;
  const p = d.picker || { value: d.range };
  const pick = { value: p.value, open: p.open, applied: p.applied, from: p.from && ymd(p.from), to: p.to && ymd(p.to) };
  return `${crumbs([["MCP server"]])}
<div class="ph"><div class="ttl"><span class="eyebrow">MCP server</span><div class="row wrap" style="gap:12px"><h1>MCP</h1>${stat}</div></div><div class="actions">${dr(pick)}</div></div>
<p class="sub muted" style="margin-top:-10px;margin-bottom:20px">Tools are generated from the API's own operations (<span class="mono">x-mcp</span>, <span class="mono">x-toolset</span>) and called through the same app: same auth, scopes, errors and audit (<span class="mono">via mcp</span>).</p>`;
}
function kpis(d, r, o) {
  if (o.loading) return `<div class="kpis">${[1, 2, 3, 4].map(() => `<div class="kpi"><span class="skel" style="width:40%;height:10px"></span><span class="skel" style="width:60%;height:24px;margin-top:12px"></span><span class="skel" style="width:70%;margin-top:10px"></span></div>`).join("")}</div>`;
  const t = d.ranges[r].totals;
  const dash = o.off ? "–" : null;
  return `<div class="kpis">
  <div class="kpi"><div class="l">Tool calls</div><div class="v" data-live-calls data-n="${t.calls}">${dash || N(t.calls)}</div><div class="d">${o.off ? `last known ${N(d.offline.lastKnownCalls)} at ${esc(d.offline.lastKnownAt)}` : r === "today" ? "since 12:00 AM PT" : "in range"}</div></div>
  <div class="kpi"><div class="l">Tokens returned · est.</div><div class="v">${dash || "≈ " + K(t.tokens)}</div><div class="d">response bytes ÷ 4</div></div>
  <div class="kpi"><div class="l">Errors</div><div class="v">${dash || N(t.errors)}</div><div class="d">${o.off ? "unknown while unreachable" : t.calls ? ((t.errors / t.calls) * 100).toFixed(1) + "% · mostly " + esc(d.errorsMostly) : "no calls"}</div></div>
  <div class="kpi"><div class="l">Clients</div><div class="v">${dash || t.clients}</div><div class="d">${o.off ? "connections dropped" : t.clients ? esc(d.clientNames.join(", ")) : "none connected"}</div></div></div>`;
}
function usage(d, r, o) {
  const R = RANGE[r];
  const hd = `<div class="hd"><div class="ttl"><span class="eyebrow">Usage</span><span>Tool calls ${R.unit}</span></div><div class="r">${R.live && !o.off && !o.zero && !o.loading ? `<span class="row" style="font-size:12px;color:var(--muted)"><span class="live"></span>Live</span>` : ""}${o.loading ? "" : legend3}</div></div>`;
  if (o.loading) return `<div class="card">${hd}<div class="bd"><div class="chart" style="margin-top:14px">${Array.from({ length: 24 }, (_, i) => `<div class="col"><span class="skel" style="height:${20 + ((i * 37) % 70)}%;border-radius:4px"></span></div>`).join("")}</div><span class="skel" style="width:50%;margin-top:18px"></span></div></div>`;
  if (o.zero) return `<div class="card">${hd}<div class="empty" style="padding:40px 20px"><div class="ill">${I.mcp}</div><h3>No tool calls yet</h3><p style="margin:0 auto;max-width:420px">Connect a client to <span class="mono">/mcp</span> with a bearer token, or run the stdio bridge. Calls show up here as they happen.</p><a class="btn primary" href="${lnk("tokens.html#create")}">${I.key}Create a token</a></div></div>`;
  if (o.off) return `<div class="card">${hd}<div class="bd">${chart(d, r, true)}<div class="lastcall">${I.clock}<span>Paused. Last data ${esc(d.offline.lastData)}.</span></div></div></div>`;
  const lc = d.lastCall;
  return `<div class="card">${hd}<div class="bd">${chart(d, r)}<div class="lastcall">${I.bolt}<span>Last call</span><span class="mono" data-last-call>${esc(lc.call)}</span><span>${actor("agent", esc(lc.agent), { k: false })}</span><span class="code${lc.code === 200 ? "" : " e"}">${lc.code}</span><span data-last-meta>${callMeta(lc)}</span><span class="lc-t" data-last-t>${R.live ? "just now" : esc(lc.at)}</span></div></div></div>`;
}
const toolsetOpts = (d) => {
  const def = defTools(d), n = (ts) => d.tools.filter((x) => x.toolset === ts).length;
  return [{ v: "default", label: "Default toolsets", hint: `${def.length} tools · everything except admin` }, { group: "Toolsets" }]
    .concat(d.toolsets.filter((t) => t !== "admin").map((t) => ({ v: t, label: t, hint: `${n(t)} tools` })))
    .concat(["-", { v: "admin", label: "admin", icon: I.lock, hint: `${n("admin")} tools · off by default, ?toolsets=admin` }, { v: "all", label: "Every MCP tool", hint: `${d.tools.length} tools of about ${d.apiOps} API operations` }]);
};
function tools(d, r, o) {
  if (o.loading) return `<div class="card"><div class="tools-hd"><span class="skel" style="width:180px;height:30px;border-radius:9px"></span><span class="skel" style="width:140px;height:30px;border-radius:9px"></span></div><div class="bd">${[1, 2, 3, 4, 5, 6].map(() => `<div class="row" style="gap:18px;padding:10px 0"><span class="skel" style="width:22%"></span><span class="skel" style="width:46%"></span><span class="skel" style="width:12%"></span></div>`).join("")}</div></div>`;
  const maxTok = Math.max(...d.tools.map((t) => t.tokCall));
  const calls = (t) => N(t.calls[r]);
  const key = (t) => esc(`${t.name} ${t.desc.toLowerCase()} ${t.scope}`);
  const row = (t) => `<tr data-n="${key(t)}" data-ts="${esc(t.toolset)}"${t.toolset === "admin" ? " hidden" : ""} data-go="tool-detail"><td class="tt"><div class="tn">${esc(t.name)}</div><div class="desc">${esc(t.desc)}</div><div style="margin-top:5px">${ann(t.kind)}</div></td><td><span class="chip">${esc(t.toolset)}</span></td><td><span class="mono" style="font-size:12px">${esc(t.scope)}</span></td><td><span class="tok"><b>≈ ${K(t.tokCall)}</b><span class="meter"><i style="width:${(t.tokCall / maxTok * 100).toFixed(0)}%"></i></span></span></td><td class="num">${calls(t)}</td></tr>`;
  const mrow = (t) => `<div class="it" data-n="${key(t)}" data-ts="${esc(t.toolset)}"${t.toolset === "admin" ? " hidden" : ""} data-go="tool-detail"><div class="row"><span class="tn ell" style="flex:1;min-width:0">${esc(t.name)}</span>${ann(t.kind)}</div><span class="muted" style="font-size:12.5px">${esc(t.desc)}</span><div class="row" style="font-size:12px"><span class="chip">${esc(t.toolset)}</span><span class="mono faint">${esc(t.scope)}</span><span style="margin-left:auto" class="muted">≈ ${K(t.tokCall)} tok · ${calls(t)} calls</span></div></div>`;
  return `<div class="card"><div class="tools-hd"><div class="ttl" style="margin-right:auto"><span class="eyebrow">Tools</span><span style="font-weight:600">Available tools <span class="tcount" data-tcount>${defTools(d).length} of ${d.tools.length} · about ${d.apiOps} API operations</span></span></div>
  <label class="in-ic">${I.search}<input class="in" id="toolq" placeholder="Search tools, scopes" aria-label="Search tools"></label>
  ${dd({ value: "default", options: toolsetOpts(d), cls: "sm", pre: "Toolset", name: "toolset", label: "Toolset" })}</div>
  <div class="tbl-wrap mswap cue"><table class="t ttbl"><thead><tr><th>Tool and what it does</th><th>Toolset</th><th>Scope</th><th>Tokens / call</th><th class="num">Calls</th></tr></thead><tbody>${d.tools.map(row).join("")}<tr data-none hidden><td colspan="5"><div class="empty" style="padding:28px 12px">No tool matches.</div></td></tr></tbody></table></div>
  <div class="mlist">${d.tools.map(mrow).join("")}</div>
  <div class="bd" style="padding:14px 20px;border-top:1px solid var(--edge);font-size:12px;color:var(--muted)">Not exposed: <span class="mono">auth_*</span> and the multipart <span class="mono">attachments_upload</span> (MCP uses <span class="mono">attachments_upload_base64</span>). Tool list is filtered by the token's scopes. Token figures are estimates (response bytes ÷ 4, p50), measured per tool.</div></div>`;
}
const stdio = (base) => `test-junkie-tcms mcp --url ${base} --token-env TJ_TCMS_TOKEN`;
const AUTH = "Authorization: Bearer $TJ_TCMS_TOKEN";
function connect(d) {
  const ts = d.toolsets.map((t) => tg(t !== "admin", t, `${d.tools.filter((x) => x.toolset === t).length} tools${t === "admin" ? " · off by default" : ""}`, { cls: "right sm", name: "ts:" + t })).join("");
  const copy = (txt) => `<button class="icon-btn sm" aria-label="Copy" data-copy="${esc(txt)}">${I.copy}</button>`;
  const url = `${d.connect.base}/mcp`;
  return `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Connect</span><span>Connection details</span></div></div><div class="bd">
  <div class="field"><label>Streamable HTTP</label><div class="cpy"><span class="mono" data-url>${esc(url)}</span>${copy(url)}</div></div>
  <div class="field"><label>Auth header</label><div class="cpy"><span class="mono">${AUTH}</span>${copy(AUTH)}</div><span class="hint">Any API token works; its scopes filter the tool list. <a href="${lnk("tokens.html")}">Tokens</a></span></div>
  <div class="field"><label>stdio bridge <span class="muted">· local clients</span></label><div class="cpy"><span class="mono">${esc(stdio(d.connect.base))}</span>${copy(stdio(d.connect.base))}</div></div>
  <div class="field mb0"><label>Toolsets <span class="muted">· ?toolsets=</span></label><div class="tg-list" data-tsl>${ts}</div><span class="hint" data-ctx>${defTools(d).length} tools · ≈ ${ctxTokens(defTools(d))} tokens of agent context to list them</span></div>
  </div></div>`;
}
const updates = (d) => `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Updates</span><span>Tool list, drift guard, version</span></div></div>
  <ul class="feed">${d.updates.map((u) => `<li><span class="fi ${u.kind}">${I[u.icon]}</span><div><b>${esc(u.title)}</b><p>${esc(u.text)}</p><div class="fm">${esc(u.at)}</div></div></li>`).join("")}</ul></div>`;

function screen(d) {
  const r = d.range;
  const o = { loading: d.loading, off: !d.server.up, zero: d.server.up && !d.loading && d.ranges[r].totals.calls === 0 };
  const banner = o.off ? `<div class="banner err">${I.xcirc}<div style="flex:1;min-width:0"><b>The MCP endpoint is not answering.</b> Error, as received:<pre class="raw">${esc(d.offline.error)}</pre></div><div class="r"><button class="btn sm" data-retry>${I.restore}Retry</button></div></div>` : "";
  return head(d, o) + banner + kpis(d, r, o) + `<div class="split r"><div class="mmain">${usage(d, r, o)}${tools(d, r, o)}</div><div class="mside">${connect(d)}${updates(d)}</div></div>`;
}

/* ---- tool detail drawer ---- */
function drawer(d) {
  const x = d.detail;
  const t = d.tools.find((y) => y.name === x.tool);
  return `<div class="drw-back" data-go="today"></div><aside class="drw" role="dialog" aria-modal="true" aria-label="Tool ${esc(t.name)}">
  <div class="dh"><span class="dd-ic" style="color:var(--accent-text)">${I.mcp}</span><h2>${esc(t.name)}</h2>${ann(t.kind)}<button class="icon-btn" aria-label="Close" data-go="today">${I.x}</button></div>
  <div class="db">
    <p style="margin:0">${esc(t.desc)} Every call writes a new immutable <span class="mono">case_version</span> and an audit event with <span class="mono">via mcp</span>, the agent and the person it acts for.</p>
    <div class="kvg">
      <div><span class="eyebrow">Toolset</span><div class="v"><span class="chip">${esc(t.toolset)}</span></div></div>
      <div><span class="eyebrow">Scope</span><div class="v mono">${esc(t.scope)}</div></div>
      <div><span class="eyebrow">Operation</span><div class="v mono">${esc(t.name)} · ${esc(x.path)}</div></div>
      <div><span class="eyebrow">Calls today</span><div class="v">${t.calls.today} · ${x.errorsToday} errors</div></div></div>
    <div><div class="eyebrow" style="color:var(--faint);margin-bottom:8px">Token cost · estimate</div>
      <div class="costs"><div><b>≈ ${K(t.tokDef)}</b><span>definition, in the tool list</span></div><div><b>≈ ${K(t.tokCall)}</b><span>per call, p50 response</span></div><div><b>≈ ${K(x.p95)}</b><span>per call, p95 (long steps)</span></div></div></div>
    <div><div class="eyebrow" style="color:var(--faint);margin-bottom:8px">Parameters</div>
      <div class="card"><div class="tbl-wrap cue"><table class="t calls"><thead><tr><th>Arg</th><th>Type</th><th>Req.</th><th>Notes</th></tr></thead><tbody>${x.params.map((p) => `<tr><td><div class="mono" style="white-space:nowrap">${esc(p.arg)}</div><div class="faint" style="font-size:11.5px;margin-top:2px">${esc(p.where)}</div></td><td class="mono" style="font-size:12px">${esc(p.type)}</td><td>${p.required ? `<span class="chip acc">yes</span>` : ""}</td><td class="muted" style="font-size:12.5px">${esc(p.note)}</td></tr>`).join("")}</tbody></table></div></div>
      <p class="muted" style="font-size:12px;margin:10px 0 0"><span class="mono">Authorization</span> and <span class="mono">X-TCMS-Via</span> are set by the dispatcher and never exposed as args.</p></div>
    <div><div class="eyebrow" style="color:var(--faint);margin-bottom:8px">Recent calls</div>
      <div class="card"><div class="tbl-wrap cue"><table class="t calls"><thead><tr><th>When</th><th>Caller</th><th>Result</th><th class="num">Time</th><th class="num">Tokens</th></tr></thead><tbody>${x.calls.map((c) => `<tr><td style="white-space:nowrap">${esc(c.at)}</td><td>${actor("agent", esc(c.agent), { k: false })}<div class="muted" style="font-size:11.5px;margin-top:2px">for ${esc(person(c.for)[0])}</div></td><td><span class="code${c.code === 200 ? "" : " e"}">${c.code}</span> <span class="muted">${esc(c.note)}</span></td><td class="num">${c.ms} ms</td><td class="num">${k1(c.tokens)}</td></tr>`).join("")}</tbody></table></div></div></div>
    <div><div class="eyebrow" style="color:var(--faint);margin-bottom:8px">The ${esc(x.raw.at)} ${x.raw.code}, as returned to the agent</div><pre class="raw" style="margin:0">${esc(x.raw.body)}</pre></div>
    <div class="row wrap"><a class="btn sm" href="${lnk("audit.html#expanded")}">${I.audit}Audit event for the ${esc(x.auditAt)} call</a><button class="btn sm ghost" data-copy="${esc(t.name)}">${I.copy}Copy name</button></div>
  </div></aside>`;
}

/* ---- live behaviour (browser only, from after) ---- */
let cur = null;
let TIMER = null;
const stopLive = () => { if (TIMER) { clearInterval(TIMER); TIMER = null; } };
function startLive(main, d) {
  stopLive();
  const col = main.querySelector(".chart .col.now"), chartEl = main.querySelector(".chart"), kpi = main.querySelector("[data-live-calls]");
  if (!col || !chartEl || !kpi) return;
  const max = +chartEl.dataset.max;
  let a = +col.dataset.a, n = +kpi.dataset.n, k = 0;
  TIMER = setInterval(() => {
    if (!document.body.contains(col)) { stopLive(); return; }
    const add = 1 + Math.floor(Math.random() * 3);
    a += add; n += add; k = (k + 1) % d.liveFeed.length;
    const ia = col.querySelector("i.a");
    if (ia) ia.style.height = Math.min(88, a / max * 100).toFixed(2) + "%";
    kpi.textContent = N(n);
    const L = d.liveFeed[k], lc = main.querySelector(".lastcall");
    if (lc) {
      lc.querySelector("[data-last-call]").textContent = L.call;
      lc.querySelector(".actor span:not(.av)").textContent = L.agent;
      const code = lc.querySelector(".code"); code.textContent = L.code; code.classList.toggle("e", L.code !== 200);
      lc.querySelector("[data-last-meta]").textContent = callMeta(L);
      lc.querySelector("[data-last-t]").textContent = "just now";
    }
  }, 1800);
}

let CUR_TS = "default";
function filterTools() {
  const main = document.getElementById("main"), q = ((main.querySelector("#toolq") || {}).value || "").toLowerCase().trim();
  let shown = 0;
  main.querySelectorAll("[data-ts][data-n]").forEach((el) => {
    const ts = el.dataset.ts;
    const inTs = CUR_TS === "all" || (CUR_TS === "default" ? ts !== "admin" : ts === CUR_TS);
    const hit = inTs && (!q || el.dataset.n.includes(q));
    el.hidden = !hit;
    if (hit && el.tagName === "TR") shown++;
  });
  const none = main.querySelector("[data-none]"); if (none) none.hidden = shown > 0;
  const c = main.querySelector("[data-tcount]"); if (c) c.textContent = `${shown} of ${cur.tools.length}${q ? ` matching "${q}"` : ` · about ${cur.apiOps} API operations`}`;
}
/* document listeners, added once; they read the data of the state on screen (cur) */
let wired = false;
function wire() {
  if (wired) return;
  wired = true;
  window.addEventListener("pagehide", stopLive);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && document.querySelector(".drw")) location.hash = "today"; });
  document.addEventListener("dd:change", (e) => { if (e.detail.name === "toolset") { CUR_TS = e.detail.value; filterTools(); } });
  document.addEventListener("input", (e) => { if (e.target.id === "toolq") filterTools(); });
  document.addEventListener("change", (e) => {
    const box = e.target.closest("[data-tsl]");
    if (!box) return;
    const on = [...box.querySelectorAll("input")].filter((i) => i.checked).map((i) => i.name.slice(3));
    const isDef = on.length === cur.toolsets.filter((t) => t !== "admin").length && !on.includes("admin");
    const url = `${cur.connect.base}/mcp` + (isDef ? "" : "?toolsets=" + (on.join(",") || "none"));
    const u = document.querySelector("[data-url]"); u.textContent = url; u.nextElementSibling.dataset.copy = url;
    const sel = cur.tools.filter((t) => on.includes(t.toolset));
    document.querySelector("[data-ctx]").textContent = `${sel.length} tools · ≈ ${ctxTokens(sel)} tokens of agent context to list them`;
  });
  document.addEventListener("click", (e) => {
    const go = e.target.closest("[data-go]");
    if (go) { location.hash = go.dataset.go; return; }
    if (e.target.closest("[data-retry]")) { toast("<b>Retrying…</b>"); return; }
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    try { navigator.clipboard && navigator.clipboard.writeText(b.dataset.copy).catch(() => {}); } catch (err) { /* file:// may refuse; the toast still shows */ }
    toast(`<div><b>Copied.</b> <span class="mono muted">${esc(b.dataset.copy.length > 48 ? b.dataset.copy.slice(0, 48) + "…" : b.dataset.copy)}</span></div>`);
  });
  document.addEventListener("dr:change", (e) => {
    const v = e.detail.value, to = v === "custom" ? "custom-applied" : v;
    if (location.hash.slice(1) !== to) location.hash = to;
  });
}
const LIVE_STATES = ["today", "7d", "14d", "30d", "tool-detail"];

export default { nav: "mcp", default: "today", states: {
  "today": { render: screen },
  "today-hover": { render: screen, after: (m) => pinTip(m.querySelector(".chart .col.now").previousElementSibling) },
  "7d": { render: screen },
  "14d": { render: screen },
  "30d": { render: screen },
  "custom-open": { render: screen },
  "custom-applied": { render: screen },
  "tool-detail": { render: (d) => screen(d) + drawer(d) },
  "empty": { render: screen },
  "offline": { render: screen },
  "loading": { render: screen }
}, after: (main, id, d) => {
  cur = d;
  wire();
  stopLive();
  CUR_TS = "default";
  document.body.classList.toggle("mcp-off", id === "offline");
  if (LIVE_STATES.includes(id)) startLive(main, d);
} };
