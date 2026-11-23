/* Invite accept, outside the app shell (?view=accept&token=...). Signed out: name and password make the account
   and join the org. Signed in: it shows who is signed in, and Accept joins as them. Either way it lands on Products; a refusal
   shows the server's answer raw. The data and the call are data/accept.js. */
import { I, esc } from "../ui.js";
import { brand, field, href, rawBanner, spin } from "../shell.js";
import { actions, failure } from "../data/accept.js";

/* sign in, then come back to this invite */
const signinHere = (d) => href("signin", { next: href("accept", { token: d.token }) });

const dead = (d) => `${brand()}<section class="card"><div class="bd">
    <div class="dead-ic">${I.lock}</div>
    <h1>This invite can't be used</h1><p class="lede">Ask the admin who invited you for a new invite. If you already have an account, sign in.</p>
    ${rawBanner("Couldn't open the invite.", d.raw)}
    <div class="actions"><a class="btn lg" href="${href("signin")}">Go to sign in</a></div></div></section>`;

function form(s, d) {
  const busy = s === "submitting";
  const top = s === "exists" ? `<div class="banner err" role="alert">${I.warn}<div style="min-width:0;flex:1"><b>You already have an account.</b> The server said:<pre class="raw">${esc(d.raw)}</pre>
      <div style="margin-top:12px"><a class="btn primary sm" href="${signinHere(d)}">Sign in to accept</a></div></div></div>`
    : s === "short" ? rawBanner(d.offline ? "No response from the server." : "Couldn't create your account.", d.raw, d.offline) : "";
  const errs = d.errors || {};
  return `${brand()}<section class="card wide"><div class="bd">
    <h1>Accept your invite</h1><p class="lede">Create your account to join the org. The invite works for 7 days.</p>
    ${top}
    <form data-accept novalidate>
      ${field({ id: "name", label: "Your name", ac: "name", ph: "Full name", v: d.name, ro: busy, err: errs.name, cls: errs.name ? "bad" : "" })}
      <div class="pair">
        ${field({ id: "password", label: "Password", type: "password", ac: "new-password", v: d.password, ro: busy, hint: "At least 8 characters", err: errs.password, cls: errs.password ? "bad" : "" })}
        ${field({ id: "confirm", label: "Confirm password", type: "password", ac: "new-password", v: d.confirm, ro: busy, err: s === "mismatch" ? "Passwords don't match" : "", cls: s === "mismatch" ? "bad" : "" })}
      </div>
      <div class="actions"><button class="btn primary lg"${busy || s === "exists" ? " disabled" : ""}>${busy ? spin + "Creating account…" : "Create account and join"}</button></div>
    </form></div></section>
    <p class="foot">Already have an account? <a href="${signinHere(d)}">Sign in to accept</a></p>`;
}

/* already signed in (the invite-exists path ends here after sign-in): accept with { token } as this user */
const signedin = (d) => `${brand()}<section class="card"><div class="bd">
    <h1>Accept your invite</h1><p class="lede">You're signed in. Accept to join the org that invited you.</p>
    <div class="who">${I.person}<div style="min-width:0"><b>${esc(d.me.name)}</b><span>${esc(d.me.email)}</span></div></div>
    <div class="actions"><button class="btn primary lg" type="button" data-accept-now>Accept invite</button>
    <button class="btn ghost" type="button" data-signout-here>Not you? Sign out</button></div></div></section>`;

const STATES = ["valid", "mismatch", "short", "submitting", "exists"];
const states = { ...Object.fromEntries(STATES.map((s) => [s, { render: (d) => form(s, d) }])), signedin: { render: signedin }, dead: { render: dead } };

/* Signed in: accept as this user, or sign out and come back here signed out. Signed out: the form checks the two
   passwords match (ours: the server has one), then sends the signup. Success lands on Products; a refusal draws
   its state with the raw answer. */
function after(main, state, d) {
  const draw = (s, more) => {
    const nd = { ...d, ...more };
    main.innerHTML = states[s].render(nd);
    after(main, s, nd);
  };
  const send = async (signup) => {
    try {
      await actions.accept(d.token, signup);
      location.assign(href("products"));
    } catch (e) {
      const f = failure(e, d.signedIn);
      draw(f.state, { ...signup, raw: f.raw, offline: !!f.offline, errors: f.errors, signedIn: false });
    }
  };
  if (state === "signedin") {
    const go = main.querySelector("[data-accept-now]");
    go.addEventListener("click", () => {
      go.disabled = true;
      send(null);
    });
    main.querySelector("[data-signout-here]").addEventListener("click", async () => {
      await actions.signOut();
      location.assign(signinHere(d));
    });
    return;
  }
  const f = main.querySelector("[data-accept]");
  if (!f || state === "submitting") return;
  f.addEventListener("submit", (e) => {
    e.preventDefault();
    const signup = { name: f.elements.name.value.trim(), password: f.elements.password.value, confirm: f.elements.confirm.value };
    if (signup.password !== signup.confirm) return draw("mismatch", { ...signup, raw: "", errors: {} });
    draw("submitting", signup);
    send(signup);
  });
}

export default { nav: "", bare: true, default: "valid", after, states };
