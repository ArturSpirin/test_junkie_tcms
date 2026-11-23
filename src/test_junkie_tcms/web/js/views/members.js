/* Members: the org's member list with roles, pending invites, inviting, changing a role and removing a member. */
import { I, crumbs, lnk, modal, dd, tg, psearch, hl, esc, actor, person } from "../ui.js";

const nm = (h) => person(h)[0];
const first = (h) => nm(h).split(" ")[0];
const roleDd = (d, v, o = {}) => dd({ value: v, cls: "sm", w: "132px", label: "Role", open: o.open, hl: o.hl, dis: o.dis,
  options: [{ group: "Role" }].concat(d.roles.map((r) => ({ v: r.role, label: r.role, hint: r.desc }))) });
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const pageTop = (d) => head("Members", `Settings · ${esc(d.ctx.org.name)}`, crumbs([["Settings"], ["Members"]]), `<a class="btn primary" href="#invite">${I.plus}Invite people</a>`);
const invites = (d) => d.pending.length + (d.sent ? 1 : 0);
const tabs = (d, cur) => `<div class="seg" role="group" aria-label="Show"><button class="${cur === "m" ? "on" : ""}" aria-pressed="${cur === "m"}" data-go="list">Members <span class="faint">${d.members.length}</span></button><button class="${cur === "p" ? "on" : ""}" aria-pressed="${cur === "p"}" data-go="pending">Pending invites <span class="faint">${d.pending.length}</span></button></div>`;

function memRow(d, m, q) {
  const role = d.roleChange && d.roleChange.handle === m.handle ? d.roleChange.role : m.role;
  const self = m.handle === d.ctx.user.handle;
  const open = d.open === m.handle;
  return `<div class="lrow${d.sel === m.handle ? " on" : ""}">${actor("person", esc(m.handle)).replace(/<span>[^<]*<\/span>/, "").replace('class="actor"', 'class="pi"')}
    <div class="m"><b class="ell">${hl(esc(nm(m.handle)), q)}${self ? ' <span class="chip" style="margin-left:6px">you</span>' : ""}</b><small class="ell">${hl(esc(m.email), q)}${m.agents ? ` · owns ${m.agents} agent${m.agents > 1 ? "s" : ""}` : ""}</small></div>
    <div class="r"><span class="when">${m.active === "now" ? "active now" : "active " + esc(m.active)}</span>${roleDd(d, role, { open, hl: open ? d.openHl : undefined, dis: self })}<a class="icon-btn" href="${self ? "#list" : "#remove-confirm"}" aria-label="Remove ${esc(nm(m.handle))}"${self ? ' aria-disabled="true" style="opacity:.4;pointer-events:none"' : ""}>${I.trash}</a></div></div>`;
}
const rolesCard = (d) => `<div class="card"><div class="hd"><h2>What each role can do</h2></div><div class="bd"><div class="roles">${d.roles.map((r) => `<div class="ro"><b>${r.role}</b><div>${esc(r.desc)}<small><code>${esc(r.scopes)}</code></small></div></div>`).join("")}</div>
  <p class="faint" style="font-size:12px;margin:14px 0 0">An agent never gets more than the role of the person who owns it. Agents and their tokens are in <a href="${lnk("tokens.html")}">API tokens and agents</a>.</p></div></div>`;

function list(d) {
  const q = d.q;
  const org = esc(d.ctx.org.name);
  const hits = q ? d.members.filter((m) => (nm(m.handle) + " " + m.email).toLowerCase().includes(q.toLowerCase())) : d.members;
  const body = hits.length ? hits.map((m) => memRow(d, m, q)).join("") : `<div class="empty"><div class="ill">${I.search}</div><h3>No members match “${esc(q)}”</h3><p class="muted" style="margin:0 auto 14px;max-width:420px">Search looks at names and email addresses. To add someone new, invite them.</p><a class="btn" href="#list">Clear search</a> <a class="btn primary" href="#invite">${I.plus}Invite people</a></div>`;
  return pageTop(d) + `<div class="sub" style="margin-bottom:16px">People who can sign in to ${org}. Their role sets what they and the agents they own may do.</div>` +
    `<div class="tools">${psearch({ q, ph: "Search members by name or email", cnt: hits.length + (hits.length === 1 ? " member" : " members"), clear: "#list" })}${tabs(d, "m")}</div>` +
    `<div class="g2"><div class="card"><div class="hd"><h2>Members of ${org}</h2><span class="r faint" style="font-size:12px">${hits.length} of ${d.members.length}</span></div>${body}</div>${rolesCard(d)}</div>`;
}

function pending(d) {
  const banner = d.sent ? `<div class="banner info">${I.check}<div style="flex:1"><b>${d.sent.count} invites sent.</b> They show here until each person accepts.</div></div>` : "";
  const rows = (d.sent ? [d.sent.invite] : []).concat(d.pending).map((p) => `<div class="lrow"><span class="pi"><span class="av token">${I.mail}</span></span>
    <div class="m"><b class="ell">${esc(p.email)}</b><small>${p.role} · invited by ${esc(nm(p.invitedBy))} ${esc(p.when)} · ${p.expiresIn ? `expires in ${p.expiresIn} days` : '<span style="color:var(--blocked)">expired</span>'}</small></div>
    <div class="r"><button class="btn sm">${I.mail}${p.expiresIn ? "Resend" : "Send again"}</button><a class="btn sm" href="#invite-revoked">Revoke</a></div></div>`).join("");
  return pageTop(d) + banner + `<div class="sub" style="margin-bottom:16px">Invites wait here until the person accepts. An invite works for 7 days.</div>` +
    `<div class="tools">${psearch({ q: "", ph: "Search invites by email", cnt: "" })}${tabs(d, "p")}</div>` +
    `<div class="g2"><div class="card"><div class="hd"><h2>Pending invites</h2><span class="r faint" style="font-size:12px">${invites(d)} invites</span></div>${rows}</div>${rolesCard(d)}</div>`;
}

const invite = (d) => {
  const f = d.draft;
  const err = !!f.error;
  return modal(`Invite people to ${esc(d.ctx.org.name)}`, `
  <div class="field"><label for="ie">Email addresses</label><textarea id="ie" class="in" rows="3" placeholder="One per line, or separated by commas"${err ? ' aria-invalid="true"' : ""}>${esc(f.emails.join("\n"))}</textarea>
    <small class="${err ? "err" : "hint"}">${err ? esc(f.error) : "Each person gets an email with a link that works for 7 days."}</small></div>
  <div class="field"><label>Role</label>${roleDd(d, f.role)}<small class="hint">You can change it later. Admins can invite up to admin; only owners can invite owners.</small></div>
  ${tg(false, "Send me a copy of the invite email")}`,
  `<a class="btn" href="#list">Cancel</a><a class="btn primary" href="#invite-sent">Send ${f.emails.length} invite${f.emails.length === 1 ? "" : "s"}</a>`);
};

const removeM = (d) => {
  const h = d.remove.handle;
  const m = d.members.find((x) => x.handle === h);
  return modal(`Remove ${esc(nm(h))}?`, `<p style="margin-top:0">${esc(first(h))} loses access to ${esc(d.ctx.org.name)} at once and is signed out. Their cases, results and comments stay, and the audit log keeps their name.</p>
  <div class="banner warn" style="margin:0">${I.warn}<div>Tokens ${esc(first(h))} created are revoked with them. Cycles assigned to ${esc(first(h))} become unassigned (${d.remove.openCycles} open).</div></div>`,
  `<a class="btn" href="#list">Cancel</a><a class="btn danger" href="#removed">Remove ${esc(first(h))}</a>`);
};

export default { nav: "members", default: "list",
  /* the Members / Pending invites switch goes to its state */
  after: (main) => {
    if (main._members) return;
    main._members = true;
    main.addEventListener("click", (e) => { const go = e.target.closest("[data-go]"); if (go) location.hash = go.dataset.go; });
  },
  states: {
    "list": { render: list },
    "search": { render: list },
    "search-empty": { render: list },
    "invite": { render: (d) => list(d) + invite(d) },
    "invite-error": { render: (d) => list(d) + invite(d) },
    "invite-sent": { render: pending },
    "pending": { render: pending },
    "invite-revoked": { render: pending, toast: () => `<div><b>Invite revoked.</b> <span class="muted">The link no longer works.</span></div>` },
    "change-role": { render: list },
    "role-changed": { render: list, toast: (d) => { const r = d.roleChange; return `<div><b>${esc(nm(r.handle))} is now a ${r.role}.</b> <span class="muted">Applies to ${esc(first(r.handle))}'s agents at once.</span></div>`; } },
    "remove-confirm": { render: (d) => list(d) + removeM(d) },
    "removed": { render: list, toast: (d) => `<div><b>${esc(nm(d.removed))} was removed.</b> <span class="muted">Recorded in the audit log.</span></div>` }
  }
};
