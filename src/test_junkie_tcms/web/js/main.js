/* Entry point: ?view=<view> picks the view, ?id= and the other query params pick what it shows, the hash holds
   its UI state, and ?q=<query> on the cases view is the top-bar search. */
import { configure, install } from "./ui.js";
import { context, signOut } from "./data/context.js";
import { errorBanner, href, mount } from "./shell.js";

// each view has its markup in views/<view>.js and its API adapter in data/<view>.js
const VIEWS = ["products", "releases", "tree", "cases", "case", "versions", "plans", "cycles", "start", "run", "reports", "members", "tokens", "audit", "mcp", "consumers", "signin", "accept"];

const params = Object.fromEntries(new URLSearchParams(location.search));
const view = VIEWS.includes(params.view) ? params.view : "products";
params.view = view;
// The top-bar search fills the box on the cases view only, so it can't stick to another view's links.
const q = view === "cases" ? (params.q || "").trim() : "";
const [mod, adapter] = await Promise.all([
  import(`./views/${view}.js`),
  import(`./data/${view}.js`)
]);
let ctx = null;
if (!mod.default.bare) {
  try {
    ctx = await context(params);
  } catch (e) {
    // a 401 is already on its way to sign-in (api.js), so stop here without an uncaught error; anything else shows raw
    if (e.status === 401) await new Promise(() => {});
    document.body.innerHTML = `<main class="auth" id="main">${errorBanner(e, "Couldn't load the app.")}</main>`;
    throw e;
  }
  configure(ctx);
  document.addEventListener("click", async (e) => {
    if (!e.target.closest("[data-signout]")) return;
    await signOut();
    location.assign(href("signin", { org: null, product: null }));
  });
}
install();
await mount(view, mod.default, ctx, adapter, params, q);
