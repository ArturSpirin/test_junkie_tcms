/* Sign-in, outside the app shell: email and password, then the page it came from (?next=) or Products. A failed
   sign-in shows the server's answer raw, or the browser's own error when nothing answered. The data and the call
   are data/signin.js. */
import { I } from "../ui.js";
import { brand, field, href, rawBanner, spin } from "../shell.js";
import { actions, failure } from "../data/signin.js";

function page(s, d) {
  const busy = s === "submitting";
  const top = s === "wrong" ? rawBanner("Couldn't sign you in.", d.raw)
    : s === "offline" ? rawBanner("No response from the server.", d.raw, true)
    : s === "invite" ? `<div class="banner info">${I.mail}<div style="min-width:0;flex:1"><b>Sign in to finish accepting your invite.</b> You'll come back to the invite after you sign in.</div></div>`
    : "";
  return `${brand()}<section class="card"><div class="bd">
    <h1>Sign in</h1><p class="lede">Use the email and password for your Test Junkie TCMS account.</p>
    ${top}
    <form data-signin novalidate>
      ${field({ id: "email", label: "Email", type: "email", ac: "username", ph: "you@company.com", v: d.email, cls: s === "focus" ? "is-focus" : "", ro: busy })}
      ${field({ id: "password", label: "Password", type: "password", ac: "current-password", v: busy ? d.password : "", ro: busy, cls: s === "wrong" ? "is-focus" : "" })}
      <div class="actions"><button class="btn primary lg"${busy ? " disabled" : ""}>${busy ? spin + "Signing in…" : "Sign in"}</button></div>
    </form></div></section>
    <p class="foot">No account? Ask an admin of your org for an invite.</p>`;
}

const STATES = ["default", "focus", "submitting", "wrong", "offline", "invite"];
const states = Object.fromEntries(STATES.map((s) => [s, { render: (d) => page(s, d) }]));

/* the form's submit: show submitting, sign in, then go to next; a failure draws its state with the raw answer */
function after(main, state, d) {
  const draw = (s, more) => {
    const nd = { ...d, ...more };
    main.innerHTML = states[s].render(nd);
    after(main, s, nd);
  };
  const form = main.querySelector("[data-signin]");
  if (!form || state === "submitting") return;
  (state === "wrong" ? form.elements.password : form.elements.email).focus();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = form.elements.email.value.trim(), password = form.elements.password.value;
    draw("submitting", { email, password });
    try {
      await actions.signIn(email, password);
      location.assign(d.next || href("products"));
    } catch (err) {
      draw(failure(err).state, { email, password: "", raw: failure(err).raw });
    }
  });
}

export default { nav: "", bare: true, default: "default", after, states };
