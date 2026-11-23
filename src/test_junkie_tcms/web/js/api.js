/* The one module that talks to the TCMS API (docs/app-api-contract.md, "Common rules"). Same origin, the
   session cookie, and on every write the tj_csrf cookie echoed as X-CSRF-Token. A non-2xx answer throws an
   ApiError holding the status and the response as the server sent it (status line, Content-Type, the
   problem+json body word for word), which views show raw. A network
   failure rethrows the browser's own TypeError. A 401 sends the page to sign-in with ?next= the page it was on,
   except from the sign-in and accept views themselves. */

export class ApiError extends Error {
  constructor(status, head, text) {
    const raw = text ? `${head}\n\n${text}` : head;
    super(raw);
    this.name = "ApiError";
    this.status = status;
    this.raw = raw; // the response as sent: "HTTP/1.1 401 Unauthorized\nContent-Type: ...\n\n{...}"
    try { this.body = text ? JSON.parse(text) : {}; } catch { this.body = {}; }
  }
}

/* fetch hides the HTTP version; the browser's resource timing for the call has it ("http/1.1", "h2"). */
const VERSIONS = { "http/1.0": "HTTP/1.0", "http/1.1": "HTTP/1.1", h2: "HTTP/2", h3: "HTTP/3" };
const version = (res) => {
  const t = globalThis.performance?.getEntriesByName?.(res.url) || [];
  return VERSIONS[t.length ? t[t.length - 1].nextHopProtocol : ""] || "HTTP/1.1"; // the TCMS server speaks HTTP/1.1
};

/* The status line and Content-Type of a response, as the server sent them. */
const head = (res) => {
  const type = res.headers.get("content-type");
  return [`${version(res)} ${res.status}${res.statusText ? ` ${res.statusText}` : ""}`, ...(type ? [`Content-Type: ${type}`] : [])].join("\n");
};

/* The views a 401 never leaves: they are where a 401 leads. */
const OPEN_VIEWS = ["signin", "accept"];

export const signinHref = (next) => `?view=signin&next=${encodeURIComponent(next)}`;

const cookie = (name) => {
  const hit = String(globalThis.document?.cookie || "").split(/;\s*/).find((c) => c.startsWith(name + "="));
  return hit ? decodeURIComponent(hit.slice(name.length + 1)) : "";
};

const url = (path, query) => {
  const q = new URLSearchParams();
  // an array repeats the param (?release_status=planned&release_status=released)
  for (const [k, v] of Object.entries(query || {})) for (const x of [].concat(v)) if (x !== undefined && x !== null && x !== "") q.append(k, x);
  const s = q.toString();
  return s ? `${path}?${s}` : path;
};

function toSignin() {
  if (OPEN_VIEWS.includes(new URLSearchParams(location.search).get("view"))) return;
  location.assign(signinHref(location.pathname + location.search + location.hash));
}

/* One call. opts: { query, body, ifMatch }. Resolves to the parsed JSON body, or null for an empty one (204). */
export async function request(method, path, opts = {}) {
  const headers = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = cookie("tj_csrf");
  if (opts.ifMatch !== undefined) headers["If-Match"] = String(opts.ifMatch);
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(url(path, opts.query), {
    method, headers, credentials: "same-origin", body: opts.body === undefined ? undefined : JSON.stringify(opts.body)
  });
  const raw = await res.text();
  if (!res.ok) {
    if (res.status === 401) toSignin();
    throw new ApiError(res.status, head(res), raw);
  }
  return raw ? JSON.parse(raw) : null;
}

export const get = (path, query) => request("GET", path, { query });
export const post = (path, body, opts = {}) => request("POST", path, { ...opts, body });
export const patch = (path, body, opts = {}) => request("PATCH", path, { ...opts, body });
export const put = (path, body, opts = {}) => request("PUT", path, { ...opts, body });
export const del = (path, opts = {}) => request("DELETE", path, opts);

/* End the cookie session (auth_logout). */
export const signOut = () => post("/api/v1/auth/logout");

/* One page of a paged list: { items, total, next } (next is the cursor for the next page, or null). */
export async function page(path, query = {}) {
  const p = await get(path, query);
  return { items: p.items, total: p.total, next: p.next_cursor || null };
}

/* Every page of a paged list, for short lists the app shows whole (a switcher, a picker). */
export async function all(path, query = {}) {
  const out = [];
  let cursor = null;
  do {
    const p = await page(path, { ...query, limit: 200, cursor });
    out.push(...p.items);
    cursor = p.next;
  } while (cursor);
  return out;
}

/* The org's API path: org("acme", "products") is /api/v1/orgs/acme/products. */
export const org = (slug, ...rest) => ["/api/v1/orgs", encodeURIComponent(slug), ...rest.map((s) => encodeURIComponent(s))].join("/");

/* What a view shows for a failed call, raw: the server's response as sent, or the browser's own error. */
export const rawError = (e) => (e instanceof ApiError ? e.raw : String(e));
