// Runs the SHIPPED web/js/api.js and data/<view>.js adapters in node against a live TCMS server, the way the
// browser does: a fetch with a cookie jar (the session and tj_csrf cookies the server sets), document.cookie
// reading that jar, and a location stub that records where the page was sent.
// Usage: node adapter_harness.mjs <server url> <page url, e.g. /app?view=products>   (the test code on stdin)
// The code is the body of an async function of h, and its return value is printed as JSON. h has:
//   api                    the shipped api.js module
//   adapter(name)          the shipped data/<name>.js module (context, products, releases, signin, accept, ...)
//   ctx(params)            data/context.js context(params): what the shell gets
//   boot()                 imports the shipped main.js, as the page load does
//   signIn(email?, pw?)    sign in through the signin adapter (default: the acme owner from tests/support.py)
//   calls                  every request made: { method, path, headers, body }
//   cookies                the jar, { name: value }
//   location               the page's location; location.assigned is the URL a redirect went to, or null
//   fail(promise)          resolves to { name, status, raw } of the error the promise rejects with (or throws)
// Needs only node, no packages.
const [base, page] = process.argv.slice(2);
const JS = new URL("../../src/test_junkie_tcms/web/js/", import.meta.url);

const jar = new Map();
const calls = [];
const realFetch = globalThis.fetch;
const pageUrl = new URL(page, base);
globalThis.location = {
  pathname: pageUrl.pathname, search: pageUrl.search, hash: pageUrl.hash, assigned: null,
  assign(u) { this.assigned = u; }
};
globalThis.document = { get cookie() { return [...jar].map(([k, v]) => `${k}=${v}`).join("; "); } };
globalThis.fetch = async (path, init = {}) => {
  calls.push({ method: init.method, path, headers: { ...init.headers }, credentials: init.credentials, body: init.body ? JSON.parse(init.body) : null });
  const headers = { ...init.headers };
  if (jar.size) headers.Cookie = globalThis.document.cookie;
  const res = await realFetch(new URL(path, base), { ...init, headers, redirect: "manual" });
  for (const sc of res.headers.getSetCookie()) {
    const [pair, ...attrs] = sc.split(";");
    const name = pair.slice(0, pair.indexOf("=")).trim();
    const value = pair.slice(pair.indexOf("=") + 1).trim().replace(/^"(.*)"$/, "$1");
    if (attrs.some((a) => /^\s*max-age=0\s*$/i.test(a)) || value === "") jar.delete(name);
    else jar.set(name, value);
  }
  return res;
};

const api = await import(new URL("api.js", JS).href);
const adapter = (name) => import(new URL(`data/${name}.js`, JS).href);
const h = {
  api, adapter, calls, location: globalThis.location,
  get cookies() { return Object.fromEntries(jar); },
  ctx: async (params = {}) => (await adapter("context")).context(params),
  boot: () => import(new URL("main.js", JS).href),
  signIn: async (email = "owner@example.com", password = "correct horse battery") => (await adapter("signin")).actions.signIn(email, password),
  fail: async (p) => {
    try { await p; } catch (e) { return { name: e.name, status: e.status ?? null, raw: e.raw ?? String(e) }; }
    throw new Error("expected a failure, but the call succeeded");
  }
};
const code = await new Promise((done) => { let s = ""; process.stdin.setEncoding("utf8"); process.stdin.on("data", (c) => (s += c)); process.stdin.on("end", () => done(s)); });
const AsyncFunction = (async () => {}).constructor;
const out = await new AsyncFunction("h", code)(h);
process.stdout.write(JSON.stringify(out === undefined ? null : out));
