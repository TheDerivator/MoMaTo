// Applies the remembered appearance before the first paint, so there is no flash (APP-2).
// The same rules as js/lib/appearance.js, kept tiny because this is a classic blocking script.
(function () {
  var mode = null;
  var look = "playful";
  try {
    var stored = JSON.parse(localStorage.getItem("momato-appearance") || "null");
    if (stored && (stored.mode === "light" || stored.mode === "dark")) mode = stored.mode;
    if (stored && (stored.look === "playful" || stored.look === "boring")) look = stored.look;
  } catch (error) {
    // blocked storage: the defaults apply
  }
  var prefersDark = !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var resolved = mode || (prefersDark ? "dark" : "light");
  var root = document.documentElement;
  root.dataset.mode = resolved;
  root.dataset.look = look;
  root.style.colorScheme = resolved;
})();
