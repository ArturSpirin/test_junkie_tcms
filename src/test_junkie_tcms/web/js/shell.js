/* App shell (top bar, side nav, product and version switcher) and the state router for one view.
   Everything the shell shows about the org, user and product comes from data.context(). */
import { I, actor, dd, ddFit, esc, lnk, toast } from "./ui.js";

const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const mark = (m, cls, size = "xs") => `<span class="mark ${size}${cls ? " " + cls : ""}">${esc(m)}</span>`;

/* nav sections: [id, label, href, icon, parentId?, extra?]. The menu traces product › version › feature › case › plan › cycle › run. */
const NAVS = (ctx) => [
  ["Catalog", [
    ["products", "Products", "products.html", I.build, null, `<span class="n">${ctx.nav.products}</span>`],
    ["releases", "Versions", "releases.html", I.tag, "products"],
    ["features", "Features", "tree.html", I.tree, null, `<span class="n">${ctx.nav.features}</span>`],
    ["cases", "Cases", "cases.html", I.doc, "features"]
  ]],
  ["Planning", [["plans", "Test plans", "plans.html", I.flag, null, `<span class="n">${ctx.nav.plans}</span>`]]],
  ["Execution", [
    ["cycles", "Cycles", "cycles.html", I.cycle],
    ["run", "Run", "start.html", I.run, "cycles"]
  ]],
  ["Insights", [["reports", "Reports", "reports.html", I.report], ["audit", "Audit log", "audit.html", I.audit]]],
  ["Consumers", [["consumers", "Machines", "consumers.html", I.server, null, '<span class="chip v2">v2</span>']]],
  ["MCP server", [["mcp", "MCP", "mcp.html", I.mcp, null, ctx.mcp.up ? '<span class="live" aria-label="Server up"></span>' : ""]]],
  ["Settings", [["tokens", "Tokens and agents", "tokens.html", I.key], ["members", "Members", "members.html", I.members]]]
];

/* product and version switcher options */
const CTX = (ctx) => [
  { group: `${esc(ctx.org.name)} · products` },
  ...ctx.products.map((p) => ({ v: p.key, label: `${esc(p.key)} · ${esc(p.name)}`, hint: `${plural(p.features, "feature")} · ${plural(p.cases, "case")}`, icon: mark(p.key[0], p.markCls) })),
  "-",
  { group: `${esc(ctx.product.key)} versions` },
  ...ctx.versions.map((v) => ({ v: v.ver, label: esc(v.ver), hint: `${v.status} · ${v.when}`, icon: I.tag })),
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
  const link = ([id, label, href, ic, par, extra]) => `<a href="${lnk(href)}" class="${[par ? "sub" : "", id === nav ? "on" : "", id === parent ? "in" : ""].join(" ").trim()}"${id === nav ? ' aria-current="page"' : ""}>${ic}<span>${label}</span>${extra || ""}</a>`;
  const p = ctx.product;
  const ctxLabel = `${esc(p.key)} · ${esc(p.name)}`;
  const ctxFace = `<span class="cx"><b>${ctxLabel}</b><small>v${esc(ctx.version.ver)} · ${ctx.version.status}</small></span>`;
  const ctxDd = dd({ value: p.key, options: CTX(ctx), cls: "ctx", label: "Product and version" }).replace(`<span class="dd-v">${ctxLabel}</span>`, ctxFace);
  const me = actor("person", ctx.user.handle);
  return `
<header class="top">
  <button class="burger" aria-label="Menu" aria-expanded="false" aria-controls="side" data-nav-toggle>${I.menu}</button>
  <a class="brand" href="${lnk("tree.html")}"><span class="mark">TJ</span><span class="hide-n">Test Junkie</span> <small>TCMS</small></a>
  ${dd({ value: ctx.org.id, options: ORGS(ctx), cls: "org sm hide-n", label: "Switch org" })}
  <form class="search" role="search" data-search>${I.search}<input type="search" name="q" aria-label="Search cases" placeholder="Search cases" value="${esc(q)}" autocomplete="off" enterkeyhint="search"><kbd aria-hidden="true">/</kbd></form>
  <div class="spacer"></div>
  <div class="me">${me.replace(/<span>([^<]*)<\/span><\/span>$/, '<span class="who">$1</span></span>')}<span class="chip hide-n">${esc(ctx.user.role)}</span></div>
</header>
<nav class="side" id="side" aria-label="Main">
  ${ctxDd}
  ${NAVS(ctx).map(([h, ls], i) => `${i ? `<h6>${h}</h6>` : `<h6 style="margin-top:4px">${h}</h6>`}${ls.map(link).join("")}`).join("")}
  <div class="foot">v${esc(ctx.app.version)} · ${esc(ctx.app.hosting)}<br><span class="mono">${esc(ctx.app.openapi)}</span></div>
</nav>
<div class="scrim" data-nav-close></div>
<main class="main" id="main"></main>`;
}

/* The state to show is the URL hash (the mock's state ids); an unknown or empty hash shows the view's default. */
export const stateOf = (view, hash) => {
  const id = decodeURIComponent(hash.replace(/^#/, ""));
  const first = view.default || Object.keys(view.states)[0];
  return view.states[id] ? id : first;
};

/* Mount one view: draw the shell, then render the state in the hash, loading its data through load(state).
   q is the URL's search query (main.js reads it), shown in the top-bar search. */
export function mount(name, view, ctx, load, q = "") {
  document.body.insertAdjacentHTML("afterbegin", shell(view.nav, ctx, q));
  document.addEventListener("keydown", (e) => slashKey(e, document));
  document.querySelector("[data-search]").addEventListener("submit", (e) => {
    e.preventDefault();
    location.href = searchHref(e.currentTarget.elements.q.value);
  });
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
  let seq = 0;
  async function render() {
    const id = stateOf(view, location.hash);
    const s = view.states[id];
    const mine = ++seq;
    const d = await load(id);
    if (mine !== seq) return; // a newer hash change won
    d.ctx = ctx;
    setNav(!!s.navOpen);
    document.querySelectorAll(".toast.live-t").forEach((t) => t.remove());
    main.innerHTML = s.render(d);
    if (s.toast) toast(s.toast(d), false, s.toastKeep);
    if (s.after) s.after(main, d);
    if (view.after) view.after(main, id, d);
    document.querySelectorAll(".dd.open").forEach(ddFit);
    cues();
  }
  // a table wider than its card gets a fade on the right until it is scrolled to the end
  function cues() {
    document.querySelectorAll(".tbl-wrap").forEach((w) => {
      const set = () => { const over = w.scrollWidth > w.clientWidth + 2; w.classList.toggle("cue", over); w.classList.toggle("end", over && w.scrollLeft + w.clientWidth >= w.scrollWidth - 2); };
      if (!w._cue) { w._cue = 1; w.addEventListener("scroll", set, { passive: true }); }
      set();
    });
  }
  window.addEventListener("hashchange", render);
  window.addEventListener("resize", () => { document.querySelectorAll(".dd.open").forEach(ddFit); cues(); });
  return render();
}
