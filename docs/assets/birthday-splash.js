/* Birthday splash dismiss — static export */
(function () {
  function todayKey() {
    var d = new Date();
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return "qlu-birthday-" + y + "-" + m + "-" + day;
  }
  function isNov24(now) {
    now = now || new Date();
    return now.getMonth() === 10 && now.getDate() === 24;
  }
  function forceFromQuery() {
    try { return new URLSearchParams(window.location.search).get("birthday") === "1"; }
    catch (e) { return false; }
  }
  function shouldShow() {
    var forced = forceFromQuery();
    if (!forced && !isNov24()) return false;
    if (forceFromQuery()) return true;
    try { if (localStorage.getItem(todayKey()) === "1") return false; } catch (e) {}
    return true;
  }
  function markSeen() {
    try { localStorage.setItem(todayKey(), "1"); } catch (e) {}
  }
  function init(root) {
    if (!shouldShow()) {
      root.hidden = true;
      root.setAttribute("aria-hidden", "true");
      return;
    }
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
    document.documentElement.classList.add("birthday-splash-open");
    var dismiss = function () {
      if (root.classList.contains("is-leaving")) return;
      root.classList.add("is-leaving");
      markSeen();
      window.setTimeout(function () {
        root.hidden = true;
        root.setAttribute("aria-hidden", "true");
        document.documentElement.classList.remove("birthday-splash-open");
        root.remove();
      }, 420);
    };
    root.querySelectorAll("[data-birthday-dismiss]").forEach(function (btn) {
      btn.addEventListener("click", function (e) { e.preventDefault(); dismiss(); });
    });
    root.addEventListener("click", function (e) { if (e.target === root) dismiss(); });
    window.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        dismiss();
      }
    }, { once: true });
  }
  function boot() {
    document.querySelectorAll("[data-birthday-splash]").forEach(init);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
