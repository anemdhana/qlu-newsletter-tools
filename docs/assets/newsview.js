/* News river: section chrome + story drawer — static export */
(function () {
  function cssEscape(id) {
    if (window.CSS && CSS.escape) return CSS.escape(id);
    return String(id).replace(/([^a-zA-Z0-9_-])/g, "\\$1");
  }
  function chapterIdForEl(el) {
    var section = el && el.closest ? el.closest("[data-news-section]") : null;
    return (section && section.id) || null;
  }
  function storyParamFromUrl() {
    try {
      var raw = (new URLSearchParams(window.location.search).get("story") || "").trim();
      return raw || null;
    } catch (e) {
      return null;
    }
  }
  function urlWithStory(storyId) {
    var url = new URL(window.location.href);
    if (storyId) url.searchParams.set("story", storyId);
    else url.searchParams.delete("story");
    return url.pathname + url.search + url.hash;
  }
  function initNewsView(root) {
    var scroller =
      root.querySelector("[data-news-scroll]") ||
      root.querySelector(".nr__scroll") ||
      root.querySelector(".nreel__scroll");
    var selects = Array.prototype.slice.call(root.querySelectorAll("[data-news-section-select]"));
    var progress = root.querySelector("[data-news-progress]");
    var heading = root.querySelector("[data-news-heading]");
    var drawer = root.querySelector("[data-story-drawer]");
    var drawerMount = root.querySelector("[data-story-drawer-mount]");
    var drawerHeading = root.querySelector("#nr-drawer-heading");
    if (drawerHeading && !drawerHeading.getAttribute("data-default")) {
      drawerHeading.setAttribute("data-default", drawerHeading.textContent || "");
    }
    var sectionEls = Array.prototype.slice.call(root.querySelectorAll("[data-news-section]"));
    var uniqueSections = sectionEls
      .filter(function (el) { return el.id; })
      .map(function (el) {
        return {
          id: el.id,
          el: el,
          label: el.getAttribute("data-news-label") || (el.querySelector("h2") && el.querySelector("h2").textContent) || el.id,
        };
      });
    var drawerOpenId = null;
    var lastFocus = null;
    var skipPush = false;
    var suppressObserverUntil = 0;

    function setActive(id) {
      var match = null;
      for (var i = 0; i < uniqueSections.length; i++) {
        if (uniqueSections[i].id === id) { match = uniqueSections[i]; break; }
      }
      if (!match) return;
      selects.forEach(function (sel) {
        if (sel.value !== id) sel.value = id;
      });
      if (heading) heading.textContent = match.label;
    }

    function scrollToId(id) {
      var target = root.querySelector("#" + cssEscape(id));
      if (!target || !scroller) return;
      scroller.scrollTo({ top: Math.max(0, target.offsetTop - 8), behavior: "smooth" });
      history.replaceState(null, "", "#" + id);
      setActive(id);
    }

    function closeDrawer(opts) {
      opts = opts || {};
      if (!drawer || !drawerMount) return;
      var wasOpen = drawer.classList.contains("is-open");
      drawer.classList.remove("is-open");
      drawer.setAttribute("aria-hidden", "true");
      root.classList.remove("nr--drawer-open");
      while (drawerMount.firstChild) drawerMount.removeChild(drawerMount.firstChild);
      drawerOpenId = null;
      if (wasOpen && opts.history !== false && !skipPush) {
        history.pushState({ storyDrawer: null }, "", urlWithStory(null));
      }
      skipPush = false;
      if (lastFocus && lastFocus.focus) {
        try { lastFocus.focus({ preventScroll: true }); } catch (e) { lastFocus.focus(); }
      }
      lastFocus = null;
    }

    function openDrawer(storyId, opts) {
      opts = opts || {};
      if (!drawer || !drawerMount) return;
      var source = root.querySelector('[data-story-source="' + String(storyId).replace(/"/g, "") + '"]');
      if (!source) return;
      var titleEl = source.querySelector(".story-reader__title");
      if (drawerHeading) {
        drawerHeading.textContent =
          (titleEl && titleEl.textContent && titleEl.textContent.trim()) ||
          drawerHeading.getAttribute("data-default") ||
          "";
      }
      while (drawerMount.firstChild) drawerMount.removeChild(drawerMount.firstChild);
      var first = source.firstElementChild;
      if (first) drawerMount.appendChild(first.cloneNode(true));
      lastFocus = opts.focus || document.activeElement;
      drawerOpenId = storyId;
      drawer.classList.add("is-open");
      drawer.setAttribute("aria-hidden", "false");
      root.classList.add("nr--drawer-open");
      var backBtn = drawer.querySelector(".nr-drawer__back");
      requestAnimationFrame(function () {
        if (backBtn && backBtn.focus) {
          try { backBtn.focus({ preventScroll: true }); } catch (e) { backBtn.focus(); }
        }
      });
      var card = root.querySelector("#" + cssEscape(storyId));
      var chapterId = chapterIdForEl(card);
      if (chapterId) setActive(chapterId);
      if (opts.history !== false) {
        var url = urlWithStory(storyId);
        if (storyParamFromUrl() !== storyId) history.pushState({ storyDrawer: storyId }, "", url);
        else history.replaceState({ storyDrawer: storyId }, "", url);
      }
      var scrollPane = drawer.querySelector(".nr-drawer__scroll");
      if (scrollPane) scrollPane.scrollTop = 0;
    }

    function restoreStoryAnchor() {
      var id = decodeURIComponent((window.location.hash || "").replace(/^#/, ""));
      if (id.indexOf("story-") !== 0) return false;
      var target = root.querySelector("#" + cssEscape(id));
      if (!target || !scroller) return false;
      var chapterId = chapterIdForEl(target);
      var top = Math.max(0, target.offsetTop - 24);
      if (chapterId) setActive(chapterId);
      requestAnimationFrame(function () {
        scroller.scrollTo({ top: top, behavior: "smooth" });
        if (chapterId) window.setTimeout(function () { setActive(chapterId); }, 320);
      });
      return true;
    }

    selects.forEach(function (sel) {
      sel.addEventListener("change", function () {
        if (sel.value) scrollToId(sel.value);
      });
    });
    Array.prototype.forEach.call(root.querySelectorAll("a.nr__begin"), function (a) {
      a.addEventListener("click", function (e) {
        var id = (a.getAttribute("href") || "").replace(/^#/, "");
        if (!id) return;
        e.preventDefault();
        scrollToId(id);
      });
    });
    root.addEventListener("click", function (e) {
      var target = e.target;
      if (!(target instanceof Element)) return;
      var closeEl = target.closest("[data-story-drawer-close]");
      if (closeEl && drawer && drawer.contains(closeEl)) {
        e.preventDefault();
        closeDrawer();
        return;
      }
      var openLink = target.closest("a[data-story-drawer-open]");
      if (!openLink || !root.contains(openLink)) return;
      if (e.defaultPrevented) return;
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var storyId = openLink.getAttribute("data-story-drawer-open");
      if (!storyId) return;
      e.preventDefault();
      openDrawer(storyId, { focus: openLink });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!drawer || !drawer.classList.contains("is-open")) return;
      e.preventDefault();
      closeDrawer();
    });
    window.addEventListener("popstate", function () {
      var id = storyParamFromUrl();
      skipPush = true;
      if (id && root.querySelector('[data-story-source="' + String(id).replace(/"/g, "") + '"]')) {
        openDrawer(id, { history: false });
      } else if (drawer && drawer.classList.contains("is-open")) {
        closeDrawer({ history: false });
      }
      skipPush = false;
    });
    if (scroller && uniqueSections.length && "IntersectionObserver" in window) {
      var visible = {};
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            var id = entry.target.id;
            if (!id) return;
            if (entry.isIntersecting) visible[id] = entry.intersectionRatio;
            else delete visible[id];
          });
          if (Date.now() < suppressObserverUntil) return;
          var bestId = uniqueSections[0].id;
          var bestRatio = -1;
          uniqueSections.forEach(function (s) {
            var ratio = visible[s.id] || 0;
            if (ratio > bestRatio) { bestRatio = ratio; bestId = s.id; }
          });
          if (bestRatio > 0) setActive(bestId);
        },
        { root: scroller, rootMargin: "-12% 0px -62% 0px", threshold: [0.05, 0.15, 0.35, 0.55] }
      );
      uniqueSections.forEach(function (s) { observer.observe(s.el); });
    }
    function onScrollProgress() {
      if (!progress || !scroller) return;
      var max = Math.max(1, scroller.scrollHeight - scroller.clientHeight);
      var pct = Math.min(100, Math.max(2, (scroller.scrollTop / max) * 100));
      progress.style.width = pct + "%";
    }
    if (scroller) scroller.addEventListener("scroll", onScrollProgress, { passive: true });
    onScrollProgress();
    var hash = decodeURIComponent((window.location.hash || "").replace(/^#/, ""));
    var storyQ = storyParamFromUrl();
    if (storyQ && root.querySelector('[data-story-source="' + String(storyQ).replace(/"/g, "") + '"]')) {
      suppressObserverUntil = Date.now() + 500;
      restoreStoryAnchor();
      requestAnimationFrame(function () { openDrawer(storyQ, { history: false }); });
    } else if (hash.indexOf("story-") === 0) {
      suppressObserverUntil = Date.now() + 500;
      if (!restoreStoryAnchor() && uniqueSections[0]) setActive(uniqueSections[0].id);
    } else if (hash && uniqueSections.some(function (s) { return s.id === hash; })) {
      requestAnimationFrame(function () { scrollToId(hash); });
    } else if (uniqueSections[0]) {
      setActive(uniqueSections[0].id);
    }
  }
  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-newsview]"), initNewsView);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
