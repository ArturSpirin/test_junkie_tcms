/* App shell (top bar, side nav, product and version switcher), app URLs (href) and the router for one view.
   Everything the shell shows about the org, user and product comes from data/context.js. */
import { I, actor, dd, ddFit, esc, toast } from "./ui.js";
import { ApiError, rawError } from "./api.js";

const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const mark = (m, cls, size = "xs") => `<span class="mark ${size}${cls ? " " + cls : ""}">${esc(m)}</span>`;

/* App URLs: href("releases", { id }, "set-features") is "?view=releases&id=...#set-features". The view, its id
   and its filters live in the query; the hash holds only a UI state (a dialog, a step). The current org and
   product ride along on every link (mount sets them), unless a link sets them itself; null drops one. */
const keep = {};
export function href(view, params = {}, ui = "") {
  const q = new URLSearchParams({ view });
  for (const [k, v] of Object.entries({ ...keep, ...params })) if (v !== undefined && v !== null && v !== "") q.set(k, v);
  return `?${q}${ui ? "#" + ui : ""}`;
}

/* A failed call, shown raw: the server's problem+json body, or the browser's own error when nothing answered. */
export const rawBanner = (label, raw, offline = false) =>
  `<div class="banner err" role="alert" data-err>${offline ? I.wifioff : I.warn}<div style="min-width:0;flex:1"><b>${esc(label)}</b> ${offline ? "The browser said:" : "The server said:"}<pre class="raw">${esc(raw)}</pre></div></div>`;
/* a fetch that got no answer rejects with the browser's TypeError; any other error is the app's own, shown as is */
export const errorBanner = (e, label) => e instanceof ApiError ? rawBanner(label, rawError(e))
  : e instanceof TypeError ? rawBanner("No response from the server.", rawError(e), true)
  : `<div class="banner err" role="alert" data-err>${I.warn}<div style="min-width:0;flex:1"><b>${esc(label)}</b><pre class="raw">${esc(String(e))}</pre></div></div>`;

/* Sign-in and invite accept draw no shell: the brand above one card, with these fields. */
export const brand = () => `<a class="brand" href="${href("signin")}"><span class="mark">TJ</span><span>Test Junkie</span> <small>TCMS</small></a>`;
/* one labelled field; o: { id, label, type, ac, ph, v, cls, ro, hint, err } */
export const field = (o) => `<div class="field"><label for="${o.id}">${o.label}</label>
  <input class="in${o.cls ? " " + o.cls : ""}" id="${o.id}" name="${o.id}" type="${o.type || "text"}" autocomplete="${o.ac || "off"}"${o.ph ? ` placeholder="${o.ph}"` : ""} value="${esc(o.v || "")}"${o.ro ? " readonly" : ""}${o.err ? ' aria-invalid="true"' : ""}>
  ${o.err ? `<div class="err" role="alert">${I.warn}<span>${esc(o.err)}</span></div>` : o.hint ? `<div class="hint">${o.hint}</div>` : ""}</div>`;
export const spin = '<span class="spin" aria-hidden="true"></span>';
/* Put errorBanner(e, label) at the top of el (a dialog body, a card), replacing the one already there. */
export function showError(el, e, label) {
  el.querySelectorAll(":scope > [data-err]").forEach((x) => x.remove());
  el.insertAdjacentHTML("afterbegin", errorBanner(e, label));
}

/* nav sections: [id, label, view, icon, parentId?, extra?]. The menu traces product › version › feature › case › plan › cycle › run. */
const NAVS = (ctx) => [
  ["Catalog", [
    ["products", "Products", "products", I.build, null, `<span class="n">${ctx.nav.products}</span>`],
    ["releases", "Versions", "releases", I.tag, "products"],
    ["features", "Features", "tree", I.tree, null, `<span class="n">${ctx.nav.features}</span>`],
    ["cases", "Cases", "cases", I.doc, "features"]
  ]],
  ["Planning", [["plans", "Test plans", "plans", I.flag, null, `<span class="n">${ctx.nav.plans}</span>`]]],
  ["Execution", [
    ["cycles", "Cycles", "cycles", I.cycle],
    ["run", "Run", "start", I.run, "cycles"]
  ]],
  ["Insights", [["reports", "Reports", "reports", I.report], ["audit", "Audit log", "audit", I.audit]]],
  ["Consumers", [["consumers", "Machines", "consumers", I.server, null, '<span class="chip v2">v2</span>']]],
  ["MCP server", [["mcp", "MCP", "mcp", I.mcp, null, ctx.mcp.up ? '<span class="live" aria-label="Server up"></span>' : ""]]],
  ["Settings", [["tokens", "Tokens and agents", "tokens", I.key], ["members", "Members", "members", I.members]]]
];

/* product and version switcher options */
const CTX = (ctx) => [
  { group: `${esc(ctx.org.name)} · products` },
  ...ctx.products.map((p) => ({ v: p.key, label: `${esc(p.key)} · ${esc(p.name)}`, hint: `${plural(p.features, "feature")} · ${plural(p.cases, "case")}`, icon: mark(p.key[0], p.markCls) })),
  "-",
  ...(ctx.product ? [{ group: `${esc(ctx.product.key)} versions` }] : []),
  ...ctx.versions.map((v) => ({ v: "v:" + (v.id || v.ver), label: esc(v.ver), hint: `${v.status} · ${v.when}`, icon: I.tag })),
  "-",
  { v: "all", label: "All products…", icon: I.build }
];
const ORGS = (ctx) => [
  { group: "Your orgs" },
  ...ctx.orgs.map((o) => ({ v: o.id, label: esc(o.name), hint: `${o.role} · ${plural(o.products, "product")}`, icon: mark(o.name[0], o.markCls) })),
  "-",
  { v: "new", label: "Create org…", icon: I.plus }
];

/* The top-bar search sends its query to the cases view, which filters by it. */
export const searchHref = (q) => {
  const t = (q || "").trim();
  return t ? `?view=cases&q=${encodeURIComponent(t)}` : "?view=cases";
};

/* "/" focuses the top-bar search, unless a modifier is held, the key goes to an editable field,
   a dialog is open or the search is hidden (at narrow widths). Returns whether it acted. */
const EDITABLE = "input, textarea, select, [contenteditable]:not([contenteditable='false'])";
export function slashKey(e, doc) {
  if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return false;
  const t = e.target;
  if (t && typeof t.closest === "function" && t.closest(EDITABLE)) return false;
  if (doc.querySelector('[aria-modal="true"]')) return false;
  const box = doc.querySelector("[data-search] input");
  if (!box || !box.getClientRects().length) return false;
  e.preventDefault();
  box.focus();
  box.select();
  return true;
}

export function shell(nav, ctx, q = "") {
  const all = NAVS(ctx).flatMap((s) => s[1]);
  const cur = all.find((l) => l[0] === nav);
  const parent = cur && cur[4];
  const link = ([id, label, to, ic, par, extra]) => `<a href="${href(to)}" class="${[par ? "sub" : "", id === nav ? "on" : "", id === parent ? "in" : ""].join(" ").trim()}"${id === nav ? ' aria-current="page"' : ""}>${ic}<span>${label}</span>${extra || ""}</a>`;
  const p = ctx.product;
  const ctxLabel = p ? `${esc(p.key)} · ${esc(p.name)}` : "";
  const ctxFace = `<span class="cx"><b>${ctxLabel}</b>${ctx.version ? `<small>v${esc(ctx.version.ver)} · ${ctx.version.status}</small>` : ""}</span>`;
  // an org with no product yet has nothing to switch to: no switcher
  const ctxDd = p ? dd({ value: p.key, options: CTX(ctx), cls: "ctx", label: "Product and version" }).replace(`<span class="dd-v">${ctxLabel}</span>`, ctxFace) : "";
  const me = actor("person", ctx.user.handle);
  return `
<header class="top">
  <button class="burger" aria-label="Menu" aria-expanded="false" aria-controls="side" data-nav-toggle>${I.menu}</button>
  <a class="brand" href="${href("tree")}"><span class="mark">TJ</span><span class="hide-n">Test Junkie</span> <small>TCMS</small></a>
  ${dd({ value: ctx.org.id, options: ORGS(ctx), cls: "org sm hide-n", label: "Switch org" })}
  <form class="search" role="search" data-search>${I.search}<input type="search" name="q" aria-label="Search cases" placeholder="Search cases" value="${esc(q)}" autocomplete="off" enterkeyhint="search"><kbd aria-hidden="true">/</kbd></form>
  <div class="spacer"></div>
  <div class="me">${me.replace(/<span>([^<]*)<\/span><\/span>$/, '<span class="who">$1</span></span>')}<span class="chip hide-n">${esc(ctx.user.role)}</span><button class="icon-btn" aria-label="Sign out" title="Sign out" data-signout>${I.logout}</button></div>
</header>
<nav class="side" id="side" aria-label="Main">
  ${ctxDd}
  ${NAVS(ctx).map(([h, ls], i) => `${i ? `<h6>${h}</h6>` : `<h6 style="margin-top:4px">${h}</h6>`}${ls.map(link).join("")}`).join("")}
  <div class="foot">${ctx.app.version ? `v${esc(ctx.app.version)} · ` : ""}${esc(ctx.app.hosting)}<br><span class="mono">${esc(ctx.app.openapi)}</span></div>
</nav>
<div class="scrim" data-nav-close></div>
<main class="main" id="main"></main>`;
}

/* Where a switcher pick goes: a product keeps the view (its list), a version opens it, an org starts over. */
function switchTo(name, e) {
  const { value } = e.detail;
  const box = e.target.closest(".dd");
  if (box.classList.contains("ctx")) {
    if (value === "all") return href("products", { product: null });
    if (value.startsWith("v:")) return href("releases", { id: value.slice(2) });
    return href(name, { product: value });
  }
  if (box.classList.contains("org") && value !== "new") return href(name, { org: value, product: null });
  return "";
}

/* Mount one view. Its state comes from its adapter: adapter.load(params, ctx) resolves to { state, data }, where
   params are the URL's query (view, id, filters) plus ui, the hash's UI state; it loads again when the hash
   changes. A view with bare: true (sign-in, invite accept) draws no shell and gets no ctx. A load that fails
   shows its error raw. q is the top-bar search, shown in the search box. */
export function mount(name, view, ctx, adapter, params, q = "") {
  const frame = view.bare ? bareFrame(name) : shellFrame(name, view, ctx, q);
  const main = frame.main;
  let seq = 0;
  async function render() {
    const mine = ++seq;
    const ui = decodeURIComponent(location.hash.replace(/^#/, ""));
    let got;
    try {
      got = await adapter.load({ ...params, ui }, ctx);
    } catch (e) {
      if (mine === seq) main.innerHTML = errorBanner(e, "Couldn't load this view.");
      return;
    }
    if (mine !== seq) return; // a newer hash change won
    const { state: id, data: d } = got;
    const s = view.states[id];
    if (!s) throw new Error(`${name}: the adapter chose state "${id}", which the view does not have`);
    d.ctx = ctx;
    frame.setNav(!!s.navOpen);
    document.querySelectorAll(".toast.live-t").forEach((t) => t.remove());
    main.innerHTML = s.render(d);
    if (s.toast) toast(s.toast(d), false, s.toastKeep);
    if (s.after) s.after(main, d);
    if (view.after) view.after(main, id, d);
    document.querySelectorAll(".dd.open").forEach(ddFit);
    cues();
  }
  window.addEventListener("hashchange", render);
  return render();
}

function bareFrame(name) {
  document.body.insertAdjacentHTML("afterbegin", `<main class="auth" id="main" data-view="${name}"></main>`);
  return { main: document.getElementById("main"), setNav: () => {} };
}

function shellFrame(name, view, ctx, q) {
  for (const [k, v] of [["org", ctx.org.id], ["product", ctx.product && ctx.product.key]]) if (v) keep[k] = v;
  document.body.insertAdjacentHTML("afterbegin", shell(view.nav, ctx, q));
  document.addEventListener("keydown", (e) => slashKey(e, document));
  document.querySelector("[data-search]").addEventListener("submit", (e) => {
    e.preventDefault();
    location.href = searchHref(e.currentTarget.elements.q.value);
  });
  for (const bar of document.querySelectorAll(".top, .side")) {
    bar.addEventListener("dd:change", (e) => { const to = switchTo(name, e); if (to) location.href = to; });
  }
  const main = document.getElementById("main");
  main.dataset.view = name;
  if (view.flush) main.classList.add("flush");
  // the one writer of the menu's open state: the sidebar class and the Menu button's aria-expanded move together
  const burger = document.querySelector("[data-nav-toggle]");
  const setNav = (open) => {
    document.body.classList.toggle("nav-open", open);
    burger.setAttribute("aria-expanded", String(open));
  };
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-nav-toggle]")) setNav(burger.getAttribute("aria-expanded") !== "true");
    else if (e.target.closest("[data-nav-close]")) setNav(false);
  });
  window.addEventListener("resize", () => { document.querySelectorAll(".dd.open").forEach(ddFit); cues(); });
  return { main, setNav };
}

// a table wider than its card gets a fade on the right until it is scrolled to the end
function cues() {
  document.querySelectorAll(".tbl-wrap").forEach((w) => {
    const set = () => { const over = w.scrollWidth > w.clientWidth + 2; w.classList.toggle("cue", over); w.classList.toggle("end", over && w.scrollLeft + w.clientWidth >= w.scrollWidth - 2); };
    if (!w._cue) { w._cue = 1; w.addEventListener("scroll", set, { passive: true }); }
    set();
  });
}
