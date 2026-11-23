/* Sign-in view data (the mock's fixture, for the render test). Raw responses as the server sends them (status
   line, Content-Type, body). Demo data only. */
const P = (status, title, detail) =>
  `HTTP/1.1 ${status} ${title}\nContent-Type: application/problem+json\n\n${JSON.stringify({ type: "about:blank", title, status, detail })}`;

export default {
  base: { email: "", password: "", raw: "", next: "" },
  states: {
    submitting: { email: "dana@example.com", password: "correct horse battery" },
    wrong: { email: "dana@example.com", raw: P(401, "Unauthorized", "Wrong email or password") },
    offline: { email: "dana@example.com", raw: "TypeError: Failed to fetch" },
    invite: { next: "?view=accept&token=tji_demo" }
  }
};
