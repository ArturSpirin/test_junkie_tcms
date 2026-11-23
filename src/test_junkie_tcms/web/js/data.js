/* The one data module every view reads through. Views never fetch or hold data of their own.
   For now the data are static fixtures in js/data/: each one is { base, states }, and a state's data is base
   deep-merged with states[state] (objects merge key by key; arrays and other values replace).
   Wiring the app to the API replaces the bodies of context() and load() and keeps their signatures. */

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

/* The data one view shows in one state (the state ids are the mock's). */
export async function load(view, state) {
  const f = (await import(`./data/${view}.js`)).default;
  return clone(deepMerge(f.base, (f.states || {})[state] || {}));
}
