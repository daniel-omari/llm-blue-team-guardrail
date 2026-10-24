// Apply the saved (or system) theme before first paint, so there is no flash.
// A separate file rather than an inline script, so the page's Content-Security-Policy
// can forbid inline scripts entirely.
(function () {
  var t = null;
  try { t = localStorage.getItem("theme"); } catch (e) {}
  if (t !== "night" && t !== "day") {
    t = window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "day" : "night";
  }
  document.documentElement.dataset.theme = t;
})();
