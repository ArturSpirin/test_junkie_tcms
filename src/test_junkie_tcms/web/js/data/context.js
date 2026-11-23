/* The shell's context, from the API: who is signed in and their orgs (me_get), the org's products and the current
   product's versions for the switcher, the actor directory for names (actors_list), and the nav counts.
   The org is ?org= when the user is in it, else their first; the product is ?product=, else the products view's
   ?id=, else the first. A 401 from me_get sends the page to sign-in (api.js). */
import { all, get, org as orgPath, page, post } from "../api.js";
import { current, flatten, initials, markCls, today, when } from "./map.js";

export async function context(params = {}) {
  const me = await get("/api/v1/me");
  const orgs = me.orgs || [];
  if (!orgs.length) throw new Error("This account is not a member of any org.");
  const o = orgs.find((x) => x.slug === params.org) || orgs[0];
  const at = (...rest) => orgPath(o.slug, ...rest);
  const [products, directory, counts, server] = await Promise.all([
    all(at("products")),
    get(at("actors")),
    Promise.all(orgs.map((x) => (x.slug === o.slug ? null : page(orgPath(x.slug, "products"), { limit: 1 }).then((p) => p.total)))),
    // the server's name and version; only admins and auditors may read it, so the foot shows it only for them
    get(at("mcp", "server")).catch((e) => { if (e.status === 403) return null; throw e; })
  ]);
  const want = params.product || (params.view === "products" ? params.id : "");
  const p = products.find((x) => x.key === want || x.id === want) || products[0] || null;
  const [releases, tree, plans] = p
    ? await Promise.all([all(at("products", p.key, "releases")), get(at("products", p.key, "features")), page(at("products", p.key, "plans"), { limit: 1 })])
    : [[], { items: [] }, { total: 0 }];
  const v = current(releases);
  const people = {};
  for (const a of directory.actors) people[a.id] = [a.name, initials(a.name), markCls(a.id)];
  if (me.user_id) people[me.user_id] = [me.name || me.email, initials(me.name || me.email), ""];
  return {
    app: { version: server ? server.version : "", hosting: "self-hosted", openapi: "/api/v1/openapi.json" },
    today: today(),
    org: { id: o.slug, name: o.name },
    orgs: orgs.map((x, i) => ({ id: x.slug, name: x.name, markCls: markCls(x.slug), role: x.role, products: x.slug === o.slug ? products.length : counts[i] })),
    user: { handle: me.user_id || me.actor_id, role: o.role },
    people,
    product: p && { id: p.id, key: p.key, name: p.name },
    version: v && { id: v.id, ver: v.version, status: v.status.replace("_", " ") },
    products: products.map((x) => ({ id: x.id, key: x.key, name: x.name, markCls: markCls(x.key), features: x.feature_count, cases: x.case_count })),
    versions: releases.map((r) => ({ id: r.id, ver: r.version, status: r.status.replace("_", " "), when: when(r, "due").replace(/^Released /, "") })),
    nav: { products: products.length, features: flatten(tree.items).length, plans: plans.total },
    mcp: { up: !!server }
  };
}

export { signOut } from "../api.js";
