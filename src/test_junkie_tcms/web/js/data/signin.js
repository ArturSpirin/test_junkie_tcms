/* Sign-in adapter (docs/app-api-contract.md §0): auth_login. */
import { ApiError, post, rawError } from "../api.js";

/* Only a same-origin path or query goes in next: "/app?view=..." or "?view=...", never "//host" or "https:". */
export const safeNext = (next) => (typeof next === "string" && /^(\/(?!\/)|\?)/.test(next) ? next : "");

/* params: next, the page to go to after signing in. An invite's accept page coming here shows the invite note. */
export async function load(params) {
  const next = safeNext(params.next);
  return { state: /[?&]view=accept\b/.test(next) ? "invite" : "default", data: { email: "", password: "", raw: "", next } };
}

/* What a failed sign-in shows: the server's answer (401, 422) or, when nothing answered, the browser's error. */
export const failure = (e) => ({ state: e instanceof ApiError ? "wrong" : "offline", raw: rawError(e) });

export const actions = {
  /* resolves to MeOut; the server sets the session and CSRF cookies */
  signIn: (email, password) => post("/api/v1/auth/login", { email, password })
};
