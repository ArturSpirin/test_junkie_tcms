/* Members: the org's member list with roles, pending invites, inviting (one email and a role makes an invite
   link, shown once; no email is sent), a new link for an invite, changing a role and removing a member. The data
   and the writes are data/members.js; the search is the server's (the view never filters). */
import { I, crumbs, modal, dd, psearch, hl, esc, actor, person, toast } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions, load } from "../data/members.js";

const nm = (h) => person(h)[0];
const first = (h) => nm(h).split(" ")[0];
const roleDd = (d, v, o = {}) => dd({ value: v, cls: "sm", w: "132px", label: "Role", name: o.name, open: o.open, hl: o.hl, dis: o.dis,
  options: [{ group: "Role" }].concat(d.roles.map((r) => ({ v: r.role, label: r.role, hint: r.desc }))) });
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const pageTop = (d) => head("Members", `Settings · ${esc(d.ctx.org.name)}`, crumbs([["Settings"], ["Members"]]), `<a class="btn primary" href="#invite">${I.plus}Invite people</a>`);
const tabs = (d, cur) => `<div class="seg" role="group" aria-label="Show"><button class="${cur === "m" ? "on" : ""}" aria-pressed="${cur === "m"}" data-go="list">Members <span class="faint">${d.total}</span></button><button class="${cur === "p" ? "on" : ""}" aria-pressed="${cur === "p"}" data-go="pending">Pending invites <span class="faint">${d.pendingTotal}</span></button></div>`;

function memRow(d, m, q) {
  const role = d.roleChange && d.roleChange.handle === m.handle ? d.roleChange.role : m.role;
  const self = m.handle === d.me;
  const open = d.open === m.handle;
  return `<div class="lrow${d.sel === m.handle ? " on" : ""}" data-id="${esc(m.handle)}" data-user="${esc(m.userId)}">${actor("person", esc(m.handle)).replace(/<span>[^<]*<\/span>/, "").replace('class="actor"', 'class="pi"')}
    <div class="m"><b class="ell">${hl(esc(nm(m.handle)), q)}${self ? ' <span class="chip" style="margin-left:6px">you</span>' : ""}</b><small class="ell">${hl(esc(m.email), q)}${m.agents ? ` · owns ${m.agents} agent${m.agents > 1 ? "s" : ""}` : ""}</small></div>
    <div class="r"><span class="when">${!m.active ? "" : m.active === "now" ? "active now" : "active " + esc(m.active)}</span>${roleDd(d, role, { name: "role", open, hl: open ? d.openHl : undefined, dis: self })}<a class="icon-btn" href="${self ? "#list" : href("members", { id: m.handle }, "remove-confirm")}" aria-label="Remove ${esc(nm(m.handle))}"${self ? ' aria-disabled="true" style="opacity:.4;pointer-events:none"' : ""}>${I.trash}</a></div></div>`;
}
const rolesCard = (d) => `<div class="card"><div class="hd"><h2>What each role can do</h2></div><div class="bd"><div class="roles">${d.roles.map((r) => `<div class="ro"><b>${r.role}</b><div>${esc(r.desc)}<small><code>${esc(r.scopes)}</code></small></div></div>`).join("")}</div>
  <p class="faint" style="font-size:12px;margin:14px 0 0">An agent never gets more than the role of the person who owns it. Agents and their tokens are in <a href="${href("tokens")}">API tokens and agents</a>.</p></div></div>`;

/* d.members is what the server matched for d.q (members_list?q=); d.total counts every member */
function list(d) {
  const q = d.q;
  const org = esc(d.ctx.org.name);
  const hits = d.members;
  const body = hits.length ? hits.map((m) => memRow(d, m, q)).join("") : `<div class="empty"><div class="ill">${I.search}</div><h3>No members match “${esc(q)}”</h3><p class="muted" style="margin:0 auto 14px;max-width:420px">Search looks at names and email addresses. To add someone new, invite them.</p><a class="btn" href="${href("members")}">Clear search</a> <a class="btn primary" href="#invite">${I.plus}Invite people</a></div>`;
  return pageTop(d) + `<div class="sub" style="margin-bottom:16px">People who can sign in to ${org}. Their role sets what they and the agents they own may do.</div>` +
    `<div class="tools">${psearch({ q, ph: "Search members by name or email", cnt: hits.length + (hits.length === 1 ? " member" : " members"), clear: href("members") })}${tabs(d, "m")}</div>` +
    `<div class="g2"><div class="card"><div class="hd"><h2>Members of ${org}</h2><span class="r faint" style="font-size:12px">${hits.length} of ${d.total}</span></div>${body}</div>${rolesCard(d)}</div>`;
}

function pending(d) {
  const rows = d.pending.map((p) => `<div class="lrow" data-invite="${esc(p.id)}"><span class="pi"><span class="av token">${I.mail}</span></span>
    <div class="m"><b class="ell">${esc(p.email)}</b><small>${p.role} · invited by ${esc(nm(p.invitedBy))} ${esc(p.when)} · ${p.expiresIn ? `expires in ${p.expiresIn} day${p.expiresIn === 1 ? "" : "s"}` : '<span style="color:var(--blocked)">expired</span>'}</small></div>
    <div class="r"><button class="btn sm" data-act="relink" title="Revokes this invite and creates a new link">${I.link || ""}New link</button><button class="btn sm" data-act="revoke">Revoke</button></div></div>`).join("");
  return pageTop(d) + `<div class="sub" style="margin-bottom:16px">Invites wait here until the person accepts. An invite works for 7 days.</div>` +
    `<div class="tools">${psearch({ q: "", ph: "Search invites by email", cnt: "" })}${tabs(d, "p")}</div>` +
    `<div class="g2"><div class="card"><div class="hd"><h2>Pending invites</h2><span class="r faint" style="font-size:12px">${d.pendingTotal} invite${d.pendingTotal === 1 ? "" : "s"}</span></div>${rows}</div>${rolesCard(d)}</div>`;
}

/* v5: one email and a role; the server's refusal shows under the email, raw */
const invite = (d) => {
  const f = d.draft;
  const err = !!f.error;
  return modal(`Invite someone to ${esc(d.ctx.org.name)}`, `
  <div class="field"><label for="ie">Email address</label><input id="ie" class="in" type="email" value="${esc(f.email)}"${err ? ' aria-invalid="true"' : ""}>
    <small class="${err ? "err" : "hint"}">${err ? esc(f.error) : "They sign in or sign up with this email to accept. No email is sent: you get a link to send them."}</small></div>
  <div class="field"><label>Role</label>${roleDd(d, f.role, { name: "invite-role" })}<small class="hint">You can change it later. Admins can invite up to admin; only owners can invite owners.</small></div>`,
  `<a class="btn" href="#list">Cancel</a><button class="btn primary" data-act="invite">Create invite link</button>`);
};

/* the link from InviteCreated.token, shown this once */
const created = (d) => {
  const s = d.sent;
  return modal(`Invite link for ${esc(s.email)}`, `<div class="banner warn">${I.warn}<div><b>Copy it now.</b> This is the only time the link is shown. Send it to ${esc(s.email)} yourself (chat, email, anywhere).</div></div>
    <div class="field"><label>Invite link</label><div class="secret"><span>${esc(s.link)}</span><button class="btn sm" data-copy>${I.copy}Copy invite link</button></div><span class="hint">Works once, for 7 days, for <span class="mono">${esc(s.email)}</span> as a ${esc(s.role)}. Lost it? Revoke the invite and create a new link.</span></div>`,
  `<a class="btn primary" href="#pending">Done</a>`);
};

const removeM = (d) => {
  const h = d.remove.handle;
  return modal(`Remove ${esc(nm(h))}?`, `<p style="margin-top:0">${esc(first(h))} loses access to ${esc(d.ctx.org.name)} at once and is signed out. Their cases, results and comments stay, and the audit log keeps their name.</p>
  <div class="banner warn" style="margin:0">${I.warn}<div>Tokens ${esc(first(h))} owns and the agents ${esc(first(h))} owns stop working with them.</div></div>`,
  `<a class="btn" href="#list">Cancel</a><button class="btn danger" data-act="remove">Remove ${esc(first(h))}</button>`);
};

/* go to a URL; the same URL again (a second revoke from invite-revoked) reloads, so the view loads again */
function go(url) {
  const u = new URL(url, location.href);
  if (u.search === location.search && u.hash === location.hash) location.reload();
  else location.assign(url);
}

/* draw what a write just returned, which only this page can show (the one-time link, a refused invite) */
async function draw(main, d, once) {
  const got = await load({ q: d.q }, d.ctx, once);
  got.data.ctx = d.ctx;
  history.replaceState(null, "", "#" + got.state);
  main.innerHTML = view.states[got.state].render(got.data);
  after(main, got.state, got.data);
}

/* every button calls the server, then shows what it answered; a failure shows raw */
function after(main, state, d) {
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
  main.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.go; }));
  const box = main.querySelector(".psearch input");
  if (box && state !== "pending" && state !== "invite-revoked" && state !== "invite-sent") box.addEventListener("keydown", (e) => {
    if (e.key === "Enter") location.href = href("members", { q: box.value.trim() || null });
  });
  const send = main.querySelector("[data-act=invite]");
  if (send) send.addEventListener("click", () => busy(send, "Couldn't create the invite.", async () => {
    const pick = main.querySelector('[data-name="invite-role"] .dd-o.sel');
    const form = { email: main.querySelector("#ie").value.trim(), role: pick ? pick.dataset.v : d.draft.role };
    let x;
    try {
      x = await actions.invite(form, d.ctx);
    } catch (e) {
      if (e.status === undefined) throw e; // no answer from the server: the banner says so
      return draw(main, d, { draft: form, raw: e.raw });
    }
    await draw(main, d, { invite: x, app: location.origin + location.pathname });
  }));
  main.querySelectorAll("[data-invite]").forEach((row) => {
    const inv = d.pending.find((p) => p.id === row.dataset.invite);
    const relink = row.querySelector("[data-act=relink]");
    relink.addEventListener("click", () => busy(relink, "Couldn't make a new link.", async () => {
      const x = await actions.relink(inv, d.ctx);
      await draw(main, d, { invite: x, app: location.origin + location.pathname });
    }));
    const revoke = row.querySelector("[data-act=revoke]");
    revoke.addEventListener("click", () => busy(revoke, "Couldn't revoke the invite.", async () => {
      await actions.revoke(inv.id, d.ctx);
      go(href("members", {}, "invite-revoked"));
    }));
  });
  const copy = main.querySelector("[data-copy]");
  if (copy) copy.addEventListener("click", () => busy(copy, "Couldn't copy the link.", async () => {
    await navigator.clipboard.writeText(d.sent.link);
    toast("<b>Invite link copied.</b>");
    copy.disabled = false;
  }));
  const remove = main.querySelector("[data-act=remove]");
  if (remove) remove.addEventListener("click", () => busy(remove, "Couldn't remove the member.", async () => {
    const m = d.members.find((x) => x.handle === d.remove.handle);
    await actions.remove(m.userId, d.ctx);
    go(href("members", { id: m.handle }, "removed"));
  }));
  main.querySelectorAll(".lrow[data-user]").forEach((row) => row.addEventListener("dd:change", async (e) => {
    if (e.detail.name !== "role") return;
    try {
      await actions.setRole(row.dataset.user, e.detail.value, d.ctx);
      go(href("members", { id: row.dataset.id, q: d.q || null }, "role-changed"));
    } catch (x) {
      err(x, "Couldn't change the role.");
    }
  }));
}

const view = { nav: "members", default: "list", after,
  states: {
    "list": { render: list },
    "search": { render: list },
    "search-empty": { render: list },
    "invite": { render: (d) => list(d) + invite(d) },
    "invite-error": { render: (d) => list(d) + invite(d) },
    "invite-sent": { render: (d) => pending(d) + created(d) },
    "pending": { render: pending },
    "invite-revoked": { render: pending, toast: () => `<div><b>Invite revoked.</b> <span class="muted">The link no longer works.</span></div>` },
    "change-role": { render: list },
    "role-changed": { render: list, toast: (d) => { const r = d.roleChange; return `<div><b>${esc(nm(r.handle))} is now a ${r.role}.</b> <span class="muted">Applies to ${esc(first(r.handle))}'s agents at once.</span></div>`; } },
    "remove-confirm": { render: (d) => list(d) + removeM(d) },
    "removed": { render: list, toast: (d) => `<div><b>${esc(nm(d.removed))} was removed.</b> <span class="muted">Recorded in the audit log.</span></div>` }
  }
};
export default view;
