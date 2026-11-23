/* Invite accept view data (the mock's fixture, for the render test). Raw bodies as the server sends them. Demo data only. */
const P = (status, title, detail, extra = {}) =>
  `HTTP/1.1 ${status} ${title}\nContent-Type: application/problem+json\n\n${JSON.stringify({ type: "about:blank", title, status, detail, ...extra })}`;
const typed = { name: "Sam Ortiz", password: "correct horse", confirm: "correct horse" };

export default {
  base: { token: "tji_demo", name: "", password: "", confirm: "", raw: "", offline: false, errors: {}, signedIn: false, me: null },
  states: {
    mismatch: { ...typed, confirm: "correct hors" },
    short: {
      name: "Sam Ortiz", password: "short", confirm: "short",
      raw: P(422, "Unprocessable Content", "Request is not valid", { errors: [{ loc: ["body", "password"], msg: "String should have at least 8 characters" }] }),
      errors: { password: "String should have at least 8 characters" }
    },
    submitting: typed,
    signedin: { signedIn: true, me: { name: "Lee Park", email: "lee@example.com" } },
    exists: { ...typed, raw: P(409, "Conflict", "An account exists for this email; sign in, then accept") },
    dead: { raw: P(410, "Gone", "Invite expired") }
  }
};
