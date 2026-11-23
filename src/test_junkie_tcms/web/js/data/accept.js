/* Invite accept adapter (docs/app-api-contract.md §0): me_get to see who is here, then invites_accept. Signed
   out, the form sends { token, name, password } and the server signs the new account in. Signed in, the view
   shows who is signed in and sends { token } when they accept. */
import { ApiError, get, post, rawError, signOut } from "../api.js";

/* params: token, from the invite link (?view=accept&token=...). */
export async function load(params) {
  const token = params.token || "";
  const data = { token, name: "", password: "", confirm: "", raw: "", offline: false, errors: {}, signedIn: false, me: null };
  let me;
  try {
    me = await get("/api/v1/me");
  } catch (e) {
    // 401: nobody is signed in (api.js leaves the accept view where it is), so the form shows
    if (e instanceof ApiError && e.status === 401) return { state: "valid", data };
    throw e;
  }
  return { state: "signedin", data: { ...data, signedIn: true, me: { name: me.name, email: me.email } } };
}

/* The state a failed accept shows, and what it shows raw. Signed in, every refusal is the dead invite (403
   another email, 404, 410, 409 already a member). Signed out: 404/410/403 dead, 409 an account exists, 422 and
   the rest under the form, with each errors[].msg under its field. */
export function failure(e, signedIn) {
  const raw = rawError(e);
  if (!(e instanceof ApiError)) return { state: "short", raw, offline: true, errors: {} };
  if (signedIn || [403, 404, 410].includes(e.status)) return { state: "dead", raw, errors: {} };
  if (e.status === 409) return { state: "exists", raw, errors: {} };
  const errors = {};
  for (const x of e.body.errors || []) {
    const f = [].concat(x.loc || []).at(-1);
    if (f === "name" || f === "password") errors[f] = errors[f] ? `${errors[f]} ${x.msg}` : x.msg;
  }
  return { state: "short", raw, errors };
}

export const actions = {
  /* resolves to MemberOut; signing up also sets the session and CSRF cookies */
  accept: (token, signup) => post("/api/v1/invites:accept", signup ? { token, name: signup.name, password: signup.password } : { token }),
  signOut
};
