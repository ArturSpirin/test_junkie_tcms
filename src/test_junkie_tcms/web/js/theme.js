/* The theme follows the system setting (prefers-color-scheme) and updates live. Loaded as a classic script in
   <head> so the first paint already has the right theme. */
(function () {
  const q = window.matchMedia("(prefers-color-scheme: dark)");
  const set = () => { document.documentElement.className = q.matches ? "dark" : "light"; };
  set();
  q.addEventListener("change", set);
})();
