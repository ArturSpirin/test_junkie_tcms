/* Tokens and agents: the API token list, the new-token form (scopes capped by role), the one-time secret,
   revoking, the agent list and the new-agent form, disabling and enabling an agent. The data and the writes are
   data/tokens.js. */
import { I, actor, modal, dd, tg, crumbs, toast, esc, person } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions, load } from "../data/tokens.js";

const ROLE_ORDER = ["viewer", "tester", "editor", "admin", "owner"];
const isAdmin = (role) => role === "admin" || role === "owner";
const first = (h) => esc(person(h)[0].split(" ")[0]);
const avIcon = (h) => { const p = person(h); return `<span class="av person${p[2] ? " " + p[2] : ""}" style="width:18px;height:18px;font-size:8px">${esc(p[1])}</span>`; };
const lock = () => I.lock.replace(/16/g, "12");
const live = (ts) => ts.filter((t) => t.status !== "revoked").length;

const tabs = (d, on) => (d.self ? `<div class="tabs"><a class="on">${I.key}My API tokens (${live(d.tokens)})</a></div>`
  : `<div class="tabs"><a class="${on === "t" ? "on" : ""}" href="#tokens">${I.key}API tokens (${live(d.tokens)})</a><a class="${on === "a" ? "on" : ""}" href="#agents">${I.agent}Agents (${d.agents.length})</a></div>`);
const head = (d, on, btn) => `${crumbs([["Settings"]])}
<div class="ph"><div><div class="eyebrow">Access</div><h1>Tokens and agents</h1></div><div class="actions">${btn}</div></div>
<p class="sub muted" style="margin-top:-10px;margin-bottom:20px">A token's rights are its scopes ∩ the owner's role ∩ its products. Secrets are shown once; we store only a hash.</p>` + tabs(d, on);
const tokBtn = `<button class="btn primary" data-go="create">${I.plus}New token</button>`;
const scp = (s) => `<span class="scp">${s.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</span>`;
const prods = (p) => (p.length ? esc(p.join(", ")) : "All products");

function tokens(d, toastHtml = "") {
  const own = (t) => actor(t.owner.kind, esc(t.owner.handle), { k: false });
  const revoke = (t, style) => (t.status !== "revoked" ? `<button class="btn sm danger"${style || ""} data-go="revoke-confirm" data-id="${esc(t.id)}">Revoke</button>` : "");
  const row = (t) => `<tr class="${t.status === "revoked" ? "dim" : ""}"><td class="tk-name"><b>${esc(t.name)}</b><span class="mono">${esc(t.prefix)}_••••</span></td><td>${own(t)}</td><td>${scp(t.scopes)}</td><td class="hide-m">${prods(t.products)}</td><td class="hide-m faint" style="font-size:12.5px">${esc(t.lastUsed)}</td><td style="font-size:12.5px;white-space:nowrap">${esc(t.expires)}</td><td><span class="pill ${t.status}">${t.status}</span></td><td>${revoke(t)}</td></tr>`;
  const mrow = (t) => `<div class="it"><div class="row"><b class="ell" style="flex:1">${esc(t.name)}</b><span class="pill ${t.status}">${t.status}</span></div><span class="mono faint" style="font-size:12px">${esc(t.prefix)}_••••</span>${scp(t.scopes)}<div class="row" style="font-size:12px">${own(t)}<span class="muted">expires ${esc(t.expires)}</span>${revoke(t, ' style="margin-left:auto"')}</div></div>`;
  return head(d, "t", tokBtn) + `<div class="card"><div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Name</th><th>Owner</th><th>Scopes</th><th class="hide-m">Products</th><th class="hide-m">Last used</th><th>Expires</th><th>Status</th><th></th></tr></thead><tbody>${d.tokens.map(row).join("")}</tbody></table></div><div class="mlist">${d.tokens.map(mrow).join("")}</div></div>` + toastHtml;
}

/* scopes as toggles; any scope above the owner's role is disabled with the reason */
function scopeToggles(d, role, on, bad) {
  return `<div class="tg-list sgrid">${d.scopes.map(({ scope: s, desc }) => {
    const ok = d.roleScopes[role].includes(s);
    const hint = ok ? esc(desc) : `<span class="lk">${lock()}</span>Above the owner's role (${role})`;
    return tg(on.includes(s), `<span class="mono">${esc(s)}</span>`, hint, { disabled: !ok, cls: "right" + (bad === s ? " bad" : ""), name: s });
  }).join("")}</div>`;
}
const ownerOpts = (d, role) => {
  const me = person(d.ctx.user.handle)[0] + " (you)";
  return [{ group: "You" }, { v: "me", label: me, short: me, icon: avIcon(d.ctx.user.handle), hint: role }, { group: "Agents you own" },
    ...d.agents.map((a) => ({ v: a.id, label: a.name, icon: I.agent, hint: "agent · " + a.role, dis: !isAdmin(role) || a.status === "disabled" })),
    "-", { v: "new", label: "New agent…", icon: I.plus }];
};
const expOpts = (x) => [{ v: "7", label: "In 7 days", hint: x[7] }, { v: "30", label: "In 30 days", hint: x[30] },
  { v: "90", label: "In 90 days", short: "In 90 days · " + x[90], hint: x[90] + " · recommended" }, { v: "365", label: "In 1 year", hint: x[365] },
  "-", { v: "custom", label: "Pick a date…", icon: I.calendar }, { v: "never", label: "Never", icon: I.warn, hint: "not for agents; admins only", danger: true }];
const prodOpts = (d) => d.products.map((p) => ({ v: p.key, label: `${p.key} · ${p.name}`, short: p.key, icon: `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>` }));

const createForm = (d, role, o = {}) => {
  const f = d.draft;
  return modal("New API token", `<div class="mform">${o.extra || ""}
  <div class="grid2"><div class="field"><label for="tn">Name</label><input id="tn" class="in" value="${esc(f.name)}"></div>
  <div class="field"><label>Owner</label>${dd({ value: f.owner, options: ownerOpts(d, role), cls: "block", name: "owner", label: "Owner", open: !!d.ownerOpen })}<span class="hint">Scopes are capped by the owner's role.</span></div></div>
  <div class="field"><div class="lbl-row">Scopes<span class="muted">· ${f.on.length} on</span><span class="scap" style="margin-left:auto">${lock()} capped by role <span class="chip">${role}</span></span></div>${scopeToggles(d, role, f.on)}</div>
  <div class="grid2"><div class="field"><label>Products</label>${dd({ value: f.products, multi: true, options: prodOpts(d), cls: "block", search: "Find a product…", name: "products", label: "Products", placeholder: "All products" })}<span class="hint">Empty means all products.</span></div>
  <div class="field"><label>Expires</label>${dd({ value: f.expiry, options: expOpts(d.expiryDates), cls: "block", name: "expiry", label: "Expires" })}<span class="hint">Owners get a warning 10 days before.</span></div></div></div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="create">Create token</button>`, "wide");
};
/* the scopes above a role, as "a, b and c" */
const above = (d, role) => {
  const s = d.scopes.map((x) => x.scope).filter((x) => !d.roleScopes[role].includes(x)).map((x) => `<span class="mono">${esc(x)}</span>`);
  return s.length > 1 ? s.slice(0, -1).join(", ") + " and " + s[s.length - 1] : s.join("");
};
const roleOf = (d) => d.roleAs || d.ctx.user.role;

function create(d) {
  const role = roleOf(d);
  const extra = above(d, role) ? `<div class="banner info">${I.info}<div>Your role is <b>${role}</b>: ${above(d, role)} are above it and can't be granted.</div></div>` : "";
  return tokens(d) + createForm(d, role, { extra });
}

function created(d) {
  const c = d.created;
  const u = esc(d.baseUrl);
  // a REST call the token can make: cases_list on its first product (or the current one), else products_list
  const p = c.products[0] || (d.ctx.product && d.ctx.product.key);
  const rest = `${u}/api/v1/orgs/${esc(encodeURIComponent(d.ctx.org.id))}/products${p ? `/${esc(encodeURIComponent(p))}/cases` : ""}`;
  return tokens(d) + modal("Token created", `<div class="banner warn">${I.warn}<div><b>Copy it now.</b> This is the only time the secret is shown.</div></div>
    <div class="field"><label>Token</label><div class="secret"><span>${esc(c.secret)}</span><button class="btn sm" data-copy>${I.copy}Copy</button></div><span class="hint">Format <span class="mono">tjt_&lt;prefix&gt;_&lt;secret&gt;</span>. The prefix <span class="mono">${esc(c.prefix)}</span> is how it appears in lists and the audit log.</span></div>
    <div class="field"><label>Use it with MCP</label><pre class="raw" style="margin:0">export TJ_TCMS_TOKEN=${esc(c.prefix)}_…
test-junkie-tcms mcp --url ${u} --token-env TJ_TCMS_TOKEN</pre><span class="hint">Or point an MCP client at <span class="mono">${u}/mcp</span> with this token as the bearer. <a href="${href("mcp")}">MCP server</a></span></div>
    <div class="field mb0"><label>Or the REST API</label><pre class="raw" style="margin:0">curl -H "Authorization: Bearer $TJ_TCMS_TOKEN" ${rest}</pre></div>`,
  `<button class="btn primary" data-go="tokens">I've copied it</button>`, "wide",
  `scopes ${c.scopes.join(", ")} · ${c.products.length ? c.products.join(", ") : "All products"} · expires ${c.expires}`, "faint");
}

function revokeConfirm(d) {
  const t = d.tokens.find((x) => x.id === d.revoke);
  return tokens(d) + modal(`Revoke “${esc(t.name)}”?`, `<p style="margin-top:0">Requests with <span class="mono">${esc(t.prefix)}_…</span> fail with 401 at once. CI jobs using it will stop reporting results. This can't be undone; create a new token instead.</p>
    <div class="row wrap" style="font-size:13px"><span class="muted">Owner</span>${actor(t.owner.kind, esc(t.owner.handle))}<span class="muted">· last used ${esc(t.lastUsed)}</span></div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn danger solid" data-act="revoke">Revoke token</button>`);
}

const revoked = (d) => tokens(d, `<div class="toast" role="status"><div><b>Token revoked.</b> <span class="muted">Audit: token.revoke by ${esc(person(d.ctx.user.handle)[0])}.</span></div></div>`);

function agents(d) {
  // the agent just disabled (?id= on agent-disabled), for the banner and the toast
  const off = d.disabled && d.agents.find((a) => a.id === d.disabled && a.status === "disabled");
  const offTok = off && d.tokens.find((t) => t.owner.kind === "agent" && t.owner.handle === off.name && t.status !== "revoked");
  const dis = (a) => a.status === "disabled";
  const row = (a) => `<tr class="${dis(a) ? "dim" : ""}"><td>${actor("agent", esc(a.name), { k: false })}<div class="muted" style="font-size:12px;margin-top:4px">${esc(a.desc)}</div></td><td>${actor("person", esc(a.owner), { k: false })}</td><td><span class="chip">${a.role}</span></td><td class="num">${a.tokens}</td><td class="hide-m faint" style="font-size:12.5px">${esc(a.lastActive)}</td><td><span class="pill ${a.status}">${a.status}</span></td><td><button class="btn sm ${dis(a) ? "" : "danger"}" data-act="${dis(a) ? "enable" : "disable"}" data-id="${esc(a.id)}">${dis(a) ? "Enable" : "Disable"}</button></td></tr>`;
  const mrow = (a) => `<div class="it"><div class="row">${actor("agent", esc(a.name), { k: false })}<span class="pill ${a.status}" style="margin-left:auto">${a.status}</span></div><span class="muted" style="font-size:12px">${esc(a.desc)}</span><div class="row" style="font-size:12px"><span>owner</span>${actor("person", esc(a.owner), { k: false })}<span class="chip">${a.role}</span></div></div>`;
  return head(d, "a", `<button class="btn primary" data-go="create-agent">${I.plus}New agent</button>`) +
    (off ? `<div class="banner warn">${I.warn}<div><b>${esc(off.name)} is disabled.</b> ${offTok ? `Its token <span class="mono">${esc(offTok.prefix)}</span> is` : "Its tokens are"} refused with 403 until it is enabled again. Its past actions stay in the audit log.</div></div>` : "") +
    `<div class="card"><div class="tbl-wrap mswap cue"><table class="t"><thead><tr><th>Agent</th><th>Owner</th><th>Role</th><th class="num">Tokens</th><th class="hide-m">Last active</th><th>Status</th><th></th></tr></thead><tbody>${d.agents.map(row).join("")}</tbody></table></div><div class="mlist">${d.agents.map(mrow).join("")}</div></div>
    <p class="muted" style="font-size:12.5px;margin-top:14px">An agent is a member with kind <span class="mono">agent</span>. It acts only through its tokens; the audit log names the agent and the person it acts for.</p>` +
    (off ? `<div class="toast" role="status"><div><b>${esc(off.name)} disabled.</b> <span class="muted">Audit: agent.disable by ${esc(person(d.ctx.user.handle)[0])}.</span></div></div>` : "");
}

function createAgent(d) {
  const a = d.agentDraft;
  const owner = d.owners.find((o) => o.handle === a.owner) || d.owners[0] || { handle: a.owner, role: "viewer" };
  const cap = `${first(owner.handle)}: ${owner.role}`;
  const ownOpts = d.owners.map((o) => ({ v: o.handle, label: person(o.handle)[0], icon: avIcon(o.handle), hint: o.role }));
  const r = (v, hint) => (ROLE_ORDER.indexOf(v) > ROLE_ORDER.indexOf(owner.role) ? { v, label: v, icon: I.lock, hint: `Above the owner's role (${cap})`, dis: true } : { v, label: v, hint });
  const roleOpts = [r("viewer", "read"), r("tester", "+ write:execution"), r("editor", "+ write:cases, write:planning"), "-", r("admin", "")];
  return agents(d) + modal("New agent", `<div class="mform">
    <div class="grid2"><div class="field"><label for="an">Name</label><input id="an" class="in" value="${esc(a.name)}"><span class="hint">Lowercase, digits and dashes. Shown in the audit log.</span></div>
    <div class="field"><label>Owner</label>${dd({ value: a.owner, options: ownOpts, cls: "block", name: "agent-owner", label: "Owner" })}<span class="hint">The person accountable for it.</span></div></div>
    <div class="field"><label for="ad">What it does</label><input id="ad" class="in" value="${esc(a.desc)}"></div>
    <div class="field"><label>Role</label>${dd({ value: a.role, options: roleOpts, cls: "block", name: "agent-role", label: "Role" })}
      <span class="hint">Capped by the owner's role (${cap}). It can't be raised above it later either.</span></div>
    <div class="tg-list">${tg(true, "Create its first token now", "Opens the token form with this agent as owner.", { cls: "right", name: "first-token" })}</div></div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="create-agent">Create agent</button>`, "wide");
}

function selfOnly(d) {
  return `<div class="banner info">${I.info}<div>Signed in as <b>${esc(person(d.self)[0])} · ${roleOf(d)}</b> with <span class="mono">tokens:self</span>: you see and manage only your own tokens. Agents need an admin.</div></div>` + tokens(d);
}

function error422(d) {
  const e = d.error;
  return tokens(d) + modal("New API token", `<div class="banner err">${I.warn}<div><b>The server refused the token.</b> Response, as sent:</div></div><pre class="raw" style="margin:0 0 20px">${esc(e.raw)}</pre>
    <div class="field mb0"><div class="lbl-row">Scopes<span class="muted">· owner ${esc(e.owner)}</span><span class="scap" style="margin-left:auto">${lock()} owner role <span class="chip">${e.ownerRole}</span></span></div>${scopeToggles(d, "admin", e.on, e.bad)}${e.bad ? `<span class="err">${I.warn}Owner ${esc(e.owner)} is a ${e.ownerRole}. Turn off ${esc(e.bad)} or change the owner.</span>` : ""}</div>`,
  `<button class="btn" data-back>Cancel</button><button class="btn primary" data-act="create">Create token</button>`, "wide");
}

/* go to a URL; the same URL again (enabling from #agents) reloads, so the view loads again */
function go(url) {
  const u = new URL(url, location.href);
  if (u.search === location.search && u.hash === location.hash) location.reload();
  else location.assign(url);
}

/* draw what a write just returned, which only this page can show (the one-time secret, a refused token) */
async function draw(main, d, once) {
  const got = await load({}, d.ctx, once);
  got.data.ctx = d.ctx;
  history.replaceState(null, "", "#" + got.state);
  main.innerHTML = view.states[got.state].render(got.data);
  after(main, got.state, got.data);
}

/* the shell's role chip shows the role this state acts with; links go to their state; every write calls the
   server, then shows what it answered; a failure shows raw */
function after(main, state, d) {
  const chip = document.querySelector(".me .chip");
  if (chip) chip.textContent = roleOf(d);
  const err = (e, label) => showError(main.querySelector(".modal .mb") || main, e, label);
  const busy = async (btn, label, work) => {
    btn.disabled = true;
    try {
      await work();
    } catch (e) {
      err(e, label);
      btn.disabled = false;
    }
  };
  const picks = (name) => [...main.querySelectorAll(`[data-name="${name}"] .dd-o.sel`)].map((o) => o.dataset.v);
  main.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.id) location.assign(href("tokens", { id: b.dataset.id }, b.dataset.go));
    else location.hash = b.dataset.go;
  }));
  main.addEventListener("dd:change", (e) => {
    if (e.detail.name === "owner" && e.detail.value === "new") location.hash = "create-agent";
  });
  const create = main.querySelector("[data-act=create]");
  if (create) create.addEventListener("click", () => busy(create, "Couldn't create the token.", async () => {
    const f = d.draft;
    const scopes = [...main.querySelectorAll(".sgrid input:checked")].map((i) => i.name);
    const form = state === "error-422" ? { name: f.name, owner: f.owner, scopes, products: f.products, expiry: f.expiry }
      : { name: main.querySelector("#tn").value.trim(), owner: picks("owner")[0] || f.owner, scopes, products: picks("products"), expiry: picks("expiry")[0] || f.expiry };
    let x;
    try {
      x = await actions.create(form, d.ctx);
    } catch (e) {
      if (e.status !== 422) throw e;
      return draw(main, d, { form, raw: e.raw });
    }
    await draw(main, d, { token: x, origin: location.origin });
  }));
  const copy = main.querySelector("[data-copy]");
  if (copy) copy.addEventListener("click", () => busy(copy, "Couldn't copy the token.", async () => {
    await navigator.clipboard.writeText(d.created.secret);
    toast("<b>Copied.</b>");
    copy.disabled = false;
  }));
  const revoke = main.querySelector("[data-act=revoke]");
  if (revoke) revoke.addEventListener("click", () => busy(revoke, "Couldn't revoke the token.", async () => {
    await actions.revoke(d.revoke, d.ctx);
    go(href("tokens", {}, "revoked"));
  }));
  main.querySelectorAll("[data-act=disable], [data-act=enable]").forEach((b) => b.addEventListener("click", () => busy(b, `Couldn't ${b.dataset.act} the agent.`, async () => {
    await actions[b.dataset.act](b.dataset.id, d.ctx);
    go(b.dataset.act === "disable" ? href("tokens", { id: b.dataset.id }, "agent-disabled") : href("tokens", {}, "agents"));
  })));
  const make = main.querySelector("[data-act=create-agent]");
  if (make) make.addEventListener("click", () => busy(make, "Couldn't create the agent.", async () => {
    const owner = d.owners.find((o) => o.handle === picks("agent-owner")[0]) || d.owners.find((o) => o.handle === d.agentDraft.owner);
    const a = await actions.createAgent({ name: main.querySelector("#an").value.trim(), ownerUserId: owner && owner.userId, desc: main.querySelector("#ad").value.trim(), role: picks("agent-role")[0] || d.agentDraft.role }, d.ctx);
    const firstToken = main.querySelector('input[name="first-token"]').checked;
    go(firstToken ? href("tokens", { owner: a.id }, "create") : href("tokens", {}, "agents"));
  }));
}

const view = { nav: "tokens", default: "tokens", after,
  states: {
    "tokens": { render: (d) => tokens(d) },
    "create": { render: create },
    "create-owner-open": { render: create },
    "created": { render: created },
    "revoke-confirm": { render: revokeConfirm },
    "revoked": { render: revoked },
    "agents": { render: agents },
    "create-agent": { render: createAgent },
    "agent-disabled": { render: agents },
    "self-only": { render: selfOnly },
    "error-422": { render: error422 }
  }
};
export default view;
