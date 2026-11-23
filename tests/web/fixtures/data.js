/* The mock's fixtures, for the render test only (tests/web/render_states.mjs): the shipped app reads the API
   through web/js/data/<view>.js adapters and never loads this folder.
   Each fixture in ./data/ is { base, states }, and a state's data is base deep-merged with states[state]
   (objects merge key by key; arrays and other values replace). */

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

export function deepMerge(base, over) {
  if (!isObj(base) || !isObj(over)) return over === undefined ? base : over;
  const out = { ...base };
  for (const [k, v] of Object.entries(over)) out[k] = deepMerge(base[k], v);
  return out;
}

const clone = (v) => JSON.parse(JSON.stringify(v));

/* Org, orgs, signed-in user, people, current product and version, nav counts, app info and today. */
export async function context() {
  return clone((await import("./data/context.js")).default);
}

/* The data one view shows in one mock state; q, when given, replaces the state's own. */
export async function load(view, state, q) {
  const f = (await import(`./data/${view}.js`)).default;
  const out = clone(deepMerge(f.base, (f.states || {})[state] || {}));
  if (q) out.q = q;
  return out;
}
