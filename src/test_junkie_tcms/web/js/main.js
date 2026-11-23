/* Entry point: ?view=<view> picks the view, the hash picks its state, ?q=<query> is the top-bar search. */
import { configure, install } from "./ui.js";
import { context, load } from "./data.js";
import { mount } from "./shell.js";

const VIEWS = ["products", "releases", "tree", "cases", "case", "versions", "plans", "cycles", "start", "run", "reports", "members", "tokens", "audit", "mcp", "consumers"];

const params = new URLSearchParams(location.search);
const asked = params.get("view");
const view = VIEWS.includes(asked) ? asked : "products";
// The search filters cases only: q on any other view is ignored, so it can't filter that view or stick to its links.
const q = view === "cases" ? (params.get("q") || "").trim() : "";
const [mod, ctx] = await Promise.all([import(`./views/${view}.js`), context()]);
configure(ctx);
install();
await mount(view, mod.default, ctx, (state) => load(view, state, q), q);
