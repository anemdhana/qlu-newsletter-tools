/* Newsletter reel (view=print): dots, jump, keyboard — static export */
(function () {
  function cssEscape(id) {
    if (window.CSS && CSS.escape) return CSS.escape(id);
    return String(id).replace(/([^a-zA-Z0-9_-])/g, "\\$1");
  }
  function initNewsletterReel(root) {
    var scroller =
      root.querySelector("[data-news-scroll]") ||
      root.querySelector(".nreel__scroll");
    if (!scroller) return;
    var slides = Array.prototype.slice.call(root.querySelectorAll(".nreel-slide"));
    var dots = Array.prototype.slice.call(root.querySelectorAll("[data-reel-dot]"));
    var jumpSelect = root.querySelector("[data-reel-jump-select]");
    var jumpChips = Array.prototype.slice.call(root.querySelectorAll("[data-reel-jump]"));
    if (!slides.length) return;

    function setActive(index) {
      dots.forEach(function (d, i) {
        d.classList.toggle("is-active", i === index);
      });
      var slide = slides[index];
      if (!slide) return;
      if (jumpSelect && jumpSelect.value !== slide.id) jumpSelect.value = slide.id;
      var group = slide.getAttribute("data-reel-group") || "";
      jumpChips.forEach(function (btn) {
        var id = btn.getAttribute("data-reel-jump") || "";
        var target = id ? root.querySelector("#" + cssEscape(id)) : null;
        var g = (target && target.getAttribute("data-reel-group")) || "";
        btn.classList.toggle("is-active", Boolean(group) && g === group);
      });
    }

    function goTo(index) {
      var i = Math.max(0, Math.min(slides.length - 1, index));
      var target = slides[i];
      if (!target) return;
      scroller.scrollTo({ top: target.offsetTop, behavior: "smooth" });
      setActive(i);
    }

    function goToId(id) {
      for (var i = 0; i < slides.length; i++) {
        if (slides[i].id === id) {
          goTo(i);
          return;
        }
      }
    }

    if ("IntersectionObserver" in window) {
      var visible = new Map();
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) visible.set(entry.target, entry.intersectionRatio);
            else visible.delete(entry.target);
          });
          var best = 0;
          var bestR = -1;
          slides.forEach(function (el, i) {
            var r = visible.get(el) || 0;
            if (r > bestR) {
              bestR = r;
              best = i;
            }
          });
          if (bestR > 0) setActive(best);
        },
        { root: scroller, threshold: [0.35, 0.55, 0.75] }
      );
      slides.forEach(function (el) { io.observe(el); });
    }

    dots.forEach(function (dot) {
      dot.addEventListener("click", function () {
        goTo(Number(dot.getAttribute("data-reel-dot") || "0"));
      });
    });
    jumpChips.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-reel-jump");
        if (id) goToId(id);
      });
    });
    if (jumpSelect) {
      jumpSelect.addEventListener("change", function () {
        if (jumpSelect.value) goToId(jumpSelect.value);
      });
    }
    root.addEventListener("keydown", function (e) {
      if (
        e.key !== "ArrowDown" &&
        e.key !== "ArrowUp" &&
        e.key !== "PageDown" &&
        e.key !== "PageUp"
      ) {
        return;
      }
      var t = e.target;
      if (t && t.closest && t.closest("input, textarea, select, [contenteditable]")) return;
      var active = -1;
      for (var i = 0; i < dots.length; i++) {
        if (dots[i].classList.contains("is-active")) {
          active = i;
          break;
        }
      }
      var cur = active >= 0 ? active : 0;
      e.preventDefault();
      goTo(e.key === "ArrowDown" || e.key === "PageDown" ? cur + 1 : cur - 1);
    });
    if (!root.hasAttribute("tabindex")) root.setAttribute("tabindex", "0");
    setActive(0);
  }
  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll(".nreel"), initNewsletterReel);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
