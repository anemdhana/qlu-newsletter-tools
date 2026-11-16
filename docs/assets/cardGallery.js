/* In-card image strip: prev/next + scroll-snap — static export */
(function () {
  function initCardGallery(root) {
    root = root || document;
    Array.prototype.forEach.call(root.querySelectorAll("[data-card-gallery]"), function (gallery) {
      if (gallery.getAttribute("data-gallery-ready") === "1") return;
      var track = gallery.querySelector("[data-card-gallery-track]");
      if (!track) return;
      var slides = Array.prototype.slice.call(track.querySelectorAll("[data-card-gallery-slide]"));
      if (slides.length < 2) return;
      gallery.setAttribute("data-gallery-ready", "1");
      var prev = gallery.querySelector("[data-card-gallery-prev]");
      var next = gallery.querySelector("[data-card-gallery-next]");
      var dots = Array.prototype.slice.call(gallery.querySelectorAll("[data-card-gallery-dot]"));
      function setActive(index) {
        dots.forEach(function (d, i) { d.classList.toggle("is-active", i === index); });
      }
      function goTo(index) {
        var i = Math.max(0, Math.min(slides.length - 1, index));
        var target = slides[i];
        if (!target) return;
        track.scrollTo({ left: target.offsetLeft, behavior: "smooth" });
        setActive(i);
      }
      function currentIndex() {
        var left = track.scrollLeft;
        var best = 0;
        var bestDist = Infinity;
        slides.forEach(function (el, i) {
          var d = Math.abs(el.offsetLeft - left);
          if (d < bestDist) { bestDist = d; best = i; }
        });
        return best;
      }
      if (prev) prev.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation(); goTo(currentIndex() - 1);
      });
      if (next) next.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation(); goTo(currentIndex() + 1);
      });
      dots.forEach(function (dot, i) {
        dot.addEventListener("click", function (e) {
          e.preventDefault(); e.stopPropagation(); goTo(i);
        });
      });
      track.addEventListener("scroll", function () { setActive(currentIndex()); }, { passive: true });
      setActive(0);
    });
  }
  function boot() { initCardGallery(document); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
