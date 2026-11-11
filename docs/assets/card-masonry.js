/* LTR masonry for [data-card-masonry] — static export */
(function () {
  var DEFAULT_MIN_COL = 192;
  var DEFAULT_GAP = 14;
  function prefersNativeGridLanes() {
    try { return typeof CSS !== "undefined" && CSS.supports("display", "grid-lanes"); }
    catch (e) { return false; }
  }
  function gapPx(el) {
    var raw = getComputedStyle(el).columnGap || getComputedStyle(el).gap || "";
    var n = parseFloat(raw);
    return Number.isFinite(n) ? n : DEFAULT_GAP;
  }
  function minColPx(el) {
    var n = parseFloat(el.getAttribute("data-masonry-min") || "");
    return Number.isFinite(n) && n > 0 ? n : DEFAULT_MIN_COL;
  }
  function layout(container) {
    if (prefersNativeGridLanes()) {
      container.classList.add("is-grid-lanes");
      container.classList.remove("is-masonry-laid");
      container.style.removeProperty("height");
      Array.prototype.forEach.call(container.children, function (child) {
        if (!(child instanceof HTMLElement)) return;
        child.style.removeProperty("position");
        child.style.removeProperty("left");
        child.style.removeProperty("top");
        child.style.removeProperty("width");
      });
      return;
    }
    var items = Array.prototype.filter.call(container.children, function (c) {
      return c instanceof HTMLElement;
    });
    if (!items.length) return;
    container.classList.remove("is-masonry-laid");
    container.style.height = "auto";
    items.forEach(function (item) {
      item.style.position = "";
      item.style.left = "";
      item.style.top = "";
      item.style.width = "";
    });
    var width = container.clientWidth;
    if (width <= 0) return;
    var gap = gapPx(container);
    var minCol = minColPx(container);
    var cols = Math.max(1, Math.floor((width + gap) / (minCol + gap)));
    var colWidth = (width - gap * (cols - 1)) / cols;
    var heights = Array.from({ length: cols }, function () { return 0; });
    items.forEach(function (item) {
      var col = 0;
      for (var i = 1; i < cols; i++) if (heights[i] < heights[col]) col = i;
      var left = col * (colWidth + gap);
      var top = heights[col];
      item.style.position = "absolute";
      item.style.left = left + "px";
      item.style.top = top + "px";
      item.style.width = colWidth + "px";
      heights[col] = top + item.offsetHeight + gap;
    });
    var maxH = Math.max.apply(null, heights) - (cols > 0 ? gap : 0);
    container.style.height = Math.max(0, maxH) + "px";
    container.classList.add("is-masonry-laid");
  }
  function init() {
    var grids = document.querySelectorAll("[data-card-masonry]");
    if (!grids.length) return;
    function runAll() { grids.forEach(layout); }
    runAll();
    if (typeof ResizeObserver !== "undefined") {
      var ro = new ResizeObserver(runAll);
      grids.forEach(function (g) { ro.observe(g); });
    } else {
      window.addEventListener("resize", runAll);
    }
    grids.forEach(function (grid) {
      grid.querySelectorAll("img").forEach(function (img) {
        if (img.complete) return;
        img.addEventListener("load", runAll, { once: true });
      });
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(runAll);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
