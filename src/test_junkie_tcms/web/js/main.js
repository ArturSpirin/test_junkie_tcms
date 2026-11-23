/* Entry point: ?view=<view> picks the view, the hash picks its state. */
import { configure, install } from "./ui.js";
import { context, load } from "./data.js";
import { mount } from "./shell.js";

const VIEWS = ["products", "releases", "tree", "cases", "case", "versions", "plans", "cycles", "start", "run", "reports", "members", "tokens", "audit", "mcp", "consumers"];

const asked = new URLSearchParams(location.search).get("view");
const view = VIEWS.includes(asked) ? asked : "products";
const [mod, ctx] = await Promise.all([import(`./views/${view}.js`), context()]);
configure(ctx);
install();
await mount(view, mod.default, ctx, (state) => load(view, state));
