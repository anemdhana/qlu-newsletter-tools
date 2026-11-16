#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snapshot the live Astro Print view (HTML + qlu.css + images + story pages)
into docs/ so GitHub Pages matches http://localhost:4321/issues/{month}/{lang}/?view=print

Example (Astro + CMS must be running):

  python scripts/export_print_snapshot.py --month 2026-11
  python scripts/export_print_snapshot.py --month 2026-11 --lang te
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASTRO = os.environ.get("ASTRO_URL", "http://localhost:4321")
DEFAULT_QLU_CSS = (
  REPO_ROOT.parent
  / "quantum-life-university-news"
  / "apps"
  / "web"
  / "src"
  / "styles"
  / "qlu.css"
)
DEFAULT_PUBLIC = (
  REPO_ROOT.parent / "quantum-life-university-news" / "apps" / "web" / "public"
)

LANGS = ("te", "en")

ATTR_URL_RE = re.compile(
  r"""(?P<attr>\b(?:src|href)=)(?P<q>["'])(?P<url>[^"']+)(?P=q)""",
  re.I,
)
CSS_URL_RE = re.compile(r"""url\((?P<q>['"]?)(?P<url>[^'")]+)(?P=q)\)""", re.I)
STORY_PATH_RE = re.compile(
  r"^/issues/(?P<month>\d{4}-\d{2})/(?P<lang>te|en)/story/(?P<section>[^/]+)/(?P<item>[^/]+)/?",
  re.I,
)
DATA_ASTRO_RE = re.compile(r"\s+data-astro-[a-z0-9_-]+=\"[^\"]*\"", re.I)
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
STYLE_VITE_RE = re.compile(
  r"<style\b[^>]*data-vite-dev-id=\"[^\"]*qlu\.css\"[^>]*>.*?</style>",
  re.I | re.S,
)
LINK_STYLESHEET_RE = re.compile(
  r"<link\b[^>]*rel=[\"']stylesheet[\"'][^>]*>",
  re.I,
)


def http_get(url: str, timeout: int = 120) -> tuple[bytes, str]:
  req = urllib.request.Request(
    url,
    headers={"User-Agent": "qlu-print-snapshot/1.0", "Accept": "*/*"},
  )
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
      return resp.read(), ctype
  except urllib.error.HTTPError as e:
    detail = e.read()[:400]
    raise SystemExit(f"GET {url} → HTTP {e.code}: {detail!r}") from e
  except urllib.error.URLError as e:
    raise SystemExit(f"Cannot reach {url} ({e.reason}). Is Astro running?") from e


def http_get_text(url: str) -> str:
  raw, ctype = http_get(url)
  charset = "utf-8"
  return raw.decode(charset, errors="replace")


def safe_name(url: str, fallback: str = "asset") -> str:
  path = urllib.parse.urlparse(url).path
  base = Path(path).name or fallback
  base = re.sub(r"[^\w.\-]+", "_", base)
  if not base or base in (".", ".."):
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{fallback}-{digest}"
  return base


def ensure_dir(path: Path) -> None:
  path.mkdir(parents=True, exist_ok=True)


def copy_or_fetch_public(astro: str, name: str, dest: Path) -> None:
  local = DEFAULT_PUBLIC / name
  if local.is_file():
    shutil.copy2(local, dest)
    print(f"  copied public/{name}")
    return
  data, _ = http_get(f"{astro.rstrip('/')}/{name.lstrip('/')}")
  dest.write_bytes(data)
  print(f"  fetched /{name}")


def write_qlu_css(dest: Path) -> None:
  if DEFAULT_QLU_CSS.is_file():
    text = DEFAULT_QLU_CSS.read_text(encoding="utf-8")
    dest.write_text(text, encoding="utf-8")
    print(f"  copied qlu.css from {DEFAULT_QLU_CSS}")
    return
  raise SystemExit(f"qlu.css not found at {DEFAULT_QLU_CSS}")


def write_client_js(assets: Path) -> None:
  masonry = assets / "card-masonry.js"
  masonry.write_text(
    r"""/* LTR masonry for [data-card-masonry] — static export */
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
""",
    encoding="utf-8",
  )

  splash = assets / "birthday-splash.js"
  splash.write_text(
    r"""/* Birthday splash dismiss — static export */
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
""",
    encoding="utf-8",
  )

  newsview = assets / "newsview.js"
  newsview.write_text(
    r"""/* News river: section chrome + story drawer — static export */
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
""",
    encoding="utf-8",
  )

  reel = assets / "newsletterReel.js"
  reel.write_text(
    r"""/* Newsletter reel (view=print): dots, jump, keyboard — static export */
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
""",
    encoding="utf-8",
  )
  print("  wrote card-masonry.js + birthday-splash.js + newsview.js + newsletterReel.js")


class AssetStore:
  def __init__(self, assets_dir: Path, astro: str):
    self.assets_dir = assets_dir
    self.media_dir = assets_dir / "media"
    self.astro = astro.rstrip("/")
    self.map: dict[str, str] = {}  # absolute or site path → relative-from-assets name
    ensure_dir(self.media_dir)

  def local_rel(self, stored_name: str, from_dir: Path) -> str:
    """Relative URL from an HTML file directory to docs/assets/{stored_name}."""
    target = (self.assets_dir / stored_name).resolve()
    start = Path(from_dir).resolve()
    rel = os.path.relpath(target, start=start).replace("\\", "/")
    return rel

  def ingest(self, url: str, *, prefer_media: bool = False) -> str | None:
    """Download/copy url; return assets-relative path like 'qlu-logo.png' or 'media/x.jpg'."""
    if not url or url.startswith(("data:", "mailto:", "#", "javascript:")):
      return None
    if url.startswith("//"):
      url = "https:" + url

    # Already mapped
    if url in self.map:
      return self.map[url]

    parsed = urllib.parse.urlparse(url)
    path = parsed.path or ""
    lower = path.lower()

    # Site-relative → Astro origin
    if url.startswith("/"):
      abs_url = self.astro + url
      key = url
    elif parsed.scheme in ("http", "https"):
      abs_url = url
      key = url
    else:
      return None

    # Skip pages / vite / non-file URLs (only keep real assets)
    if any(
      x in abs_url
      for x in (
        "/@vite/",
        "/@id/",
        "/src/",
        "astro&type=script",
        "lang.ts",
        "entrypoint.js",
        "youtube.com/",
        "youtu.be/",
        "fonts.googleapis.com",
        "fonts.gstatic.com",
      )
    ):
      return None

    is_cms_media = "/api/media/file/" in abs_url
    is_public = path in (
      "/qlu-logo.png",
      "/favicon.svg",
      "/newton-birthday.jpg",
    ) or name_from_path(path) in (
      "qlu-logo.png",
      "favicon.svg",
      "newton-birthday.jpg",
    )
    is_file_ext = bool(
      re.search(r"\.(png|jpe?g|gif|webp|svg|ico|css|woff2?|ttf|otf)(?:$|\?)", lower)
    )
    if not (is_cms_media or is_public or is_file_ext or prefer_media):
      return None
    # Never treat magazine HTML routes as assets
    if "/issues/" in path and not is_cms_media and not is_file_ext:
      return None

    name = safe_name(abs_url)
    is_media = prefer_media or is_cms_media or (
      is_file_ext and name not in ("qlu-logo.png", "favicon.svg", "newton-birthday.jpg", "qlu.css")
    )
    if name in ("qlu-logo.png", "favicon.svg", "newton-birthday.jpg") or path.endswith(".css"):
      dest = self.assets_dir / name
      stored = name
    elif is_media:
      dest = self.media_dir / name
      stored = f"media/{name}"
    else:
      dest = self.assets_dir / name
      stored = name

    if not dest.exists():
      public_candidate = DEFAULT_PUBLIC / name
      if public_candidate.is_file() and not is_cms_media:
        shutil.copy2(public_candidate, dest)
      else:
        try:
          data, _ = http_get(abs_url)
        except SystemExit as e:
          print(f"  warn skip asset {abs_url}: {e}")
          return None
        ensure_dir(dest.parent)
        dest.write_bytes(data)
      print(f"  asset {stored}")

    self.map[key] = stored
    self.map[abs_url] = stored
    return stored


def name_from_path(path: str) -> str:
  return Path(path).name


def collect_urls(html: str) -> set[str]:
  urls: set[str] = set()
  for m in ATTR_URL_RE.finditer(html):
    urls.add(m.group("url"))
  for m in CSS_URL_RE.finditer(html):
    urls.add(m.group("url").strip())
  return urls


def rewrite_html(
  html: str,
  *,
  store: AssetStore,
  from_dir: Path,
  lang_root: Path,
  docs_root: Path,
  month: str,
  lang: str,
  view: str = "print",
) -> str:
  # Drop Vite/Astro scripts, injected qlu <style>, and existing favicon (we re-add)
  html = SCRIPT_RE.sub("", html)
  html = STYLE_VITE_RE.sub("", html)
  html = LINK_STYLESHEET_RE.sub("", html)
  html = re.sub(
    r'<link\b[^>]*rel=["\']icon["\'][^>]*>',
    "",
    html,
    flags=re.I,
  )
  html = DATA_ASTRO_RE.sub("", html)

  # Map assets
  for url in sorted(collect_urls(html), key=len, reverse=True):
    stored = store.ingest(url)
    if not stored:
      continue
    local = store.local_rel(stored, from_dir)
    html = html.replace(f'"{url}"', f'"{local}"')
    html = html.replace(f"'{url}'", f"'{local}'")

  css_href = store.local_rel("qlu.css", from_dir)
  masonry_href = store.local_rel("card-masonry.js", from_dir)
  splash_href = store.local_rel("birthday-splash.js", from_dir)
  newsview_href = store.local_rel("newsview.js", from_dir)
  reel_href = store.local_rel("newsletterReel.js", from_dir)
  favicon = store.local_rel("favicon.svg", from_dir)

  head_inject = (
    f'<link rel="icon" type="image/svg+xml" href="{favicon}">'
    f'<link rel="stylesheet" href="{css_href}">'
  )
  if re.search(r"</head>", html, re.I):
    html = re.sub(r"</head>", head_inject + "</head>", html, count=1, flags=re.I)
  else:
    html = head_inject + html

  foot_parts = [
    f'<script src="{masonry_href}" defer></script>',
    f'<script src="{splash_href}" defer></script>',
  ]
  if view == "news":
    foot_parts.append(f'<script src="{newsview_href}" defer></script>')
  elif view == "print":
    # Reel needs drawer (newsview) + jump/dots (newsletterReel)
    foot_parts.append(f'<script src="{newsview_href}" defer></script>')
    foot_parts.append(f'<script src="{reel_href}" defer></script>')
  foot_inject = "".join(foot_parts)
  if re.search(r"</body>", html, re.I):
    html = re.sub(r"</body>", foot_inject + "</body>", html, count=1, flags=re.I)
  else:
    html += foot_inject

  to_lang = os.path.relpath(lang_root, start=from_dir).replace("\\", "/")
  to_other = os.path.relpath(lang_root.parent / ("en" if lang == "te" else "te"), start=from_dir).replace(
    "\\", "/"
  )
  to_catalog = os.path.relpath(docs_root / "index.html", start=from_dir).replace("\\", "/")
  page_here = f"{to_lang}/index.html".replace("/./", "/")
  page_other = f"{to_other}/index.html"

  replacements = {
    f"/issues/{month}/te/?view=print": page_here if lang == "te" else page_other,
    f"/issues/{month}/en/?view=print": page_here if lang == "en" else page_other,
    f"/issues/{month}/te?view=print": page_here if lang == "te" else page_other,
    f"/issues/{month}/en?view=print": page_here if lang == "en" else page_other,
    f"/issues/{month}/{lang}/?view=print": page_here,
    f"/issues/{month}/{lang}?view=print": page_here,
    f"/issues/{month}/te/": page_here if lang == "te" else page_other,
    f"/issues/{month}/en/": page_here if lang == "en" else page_other,
    f"/issues/{month}/te": page_here if lang == "te" else page_other,
    f"/issues/{month}/en": page_here if lang == "en" else page_other,
    f"/issues/{month}/{lang}/": page_here,
    f"/issues/{month}/{lang}": page_here,
    "/issues/": to_catalog,
    "/issues": to_catalog,
  }
  for v in ("news", "flip", "print"):
    for L in LANGS:
      target = page_here if L == lang else page_other
      replacements[f"/issues/{month}/{L}/?view={v}"] = target
      replacements[f"/issues/{month}/{L}?view={v}"] = target

  def story_sub(m: re.Match[str]) -> str:
    sm = STORY_PATH_RE.match(urllib.parse.urlparse(m.group("url")).path)
    if not sm:
      return m.group(0)
    story_file = (
      lang_root.parent
      / sm.group("lang")
      / "story"
      / sm.group("section")
      / sm.group("item")
      / "index.html"
    )
    rel = os.path.relpath(story_file, start=from_dir).replace("\\", "/")
    return f'{m.group("attr")}{m.group("q")}{rel}{m.group("q")}'

  html = ATTR_URL_RE.sub(
    lambda m: story_sub(m) if "/story/" in m.group("url") else m.group(0),
    html,
  )

  for old, new in sorted(replacements.items(), key=lambda kv: -len(kv[0])):
    html = html.replace(f'href="{old}"', f'href="{new}"')
    html = html.replace(f"href='{old}'", f"href='{new}'")

  # Back-to-newsletter links include #story-… anchors — rewrite path, keep hash
  def issue_view_sub(m: re.Match[str]) -> str:
    q = m.group("q")
    L = m.group("lang")
    frag = m.group("frag") or ""
    target = page_here if L == lang else page_other
    return f"href={q}{target}{frag}{q}"

  html = re.sub(
    rf"""href=(?P<q>["'])/issues/{re.escape(month)}/(?P<lang>te|en)/?\?(?:view|from)=(?:print|news|flip)(?P<frag>#[^"']*)?(?P=q)""",
    issue_view_sub,
    html,
    flags=re.I,
  )
  # Bare /issues/YYYY-MM/lang/#anchor (no query)
  html = re.sub(
    rf"""href=(?P<q>["'])/issues/{re.escape(month)}/(?P<lang>te|en)/?(?P<frag>#[^"']+)(?P=q)""",
    issue_view_sub,
    html,
    flags=re.I,
  )

  return html


def extract_story_paths(html: str, month: str, lang: str) -> list[tuple[str, str, str]]:
  """Return list of (section, item, abs_astro_path) for stories in this print page."""
  found: list[tuple[str, str, str]] = []
  seen: set[str] = set()
  for m in ATTR_URL_RE.finditer(html):
    url = m.group("url")
    path = urllib.parse.urlparse(url).path
    sm = STORY_PATH_RE.match(path)
    if not sm:
      continue
    if sm.group("month") != month or sm.group("lang") != lang:
      continue
    key = f"{sm.group('section')}/{sm.group('item')}"
    if key in seen:
      continue
    seen.add(key)
    found.append((sm.group("section"), sm.group("item"), path))
  return found


def snapshot_page(
  *,
  astro: str,
  path: str,
  out_file: Path,
  store: AssetStore,
  docs_root: Path,
  lang_root: Path,
  month: str,
  lang: str,
  view: str = "print",
) -> str:
  url = astro.rstrip("/") + path
  print(f"Fetching {url}")
  html = http_get_text(url)
  ensure_dir(out_file.parent)
  cleaned = rewrite_html(
    html,
    store=store,
    from_dir=out_file.parent,
    lang_root=lang_root,
    docs_root=docs_root,
    month=month,
    lang=lang,
    view=view,
  )
  out_file.write_text(cleaned, encoding="utf-8")
  print(f"  wrote {out_file.as_posix()}")
  return html  # original for story discovery


def write_catalog(docs: Path, month: str, *, view: str = "print") -> None:
  label = "News" if view == "news" else "Print reel"
  body_class = "is-news"
  main_class = "news-main nreel-main" if view == "print" else "news-main"
  catalog = docs / "index.html"
  month_index = docs / "issues" / month / "index.html"
  ensure_dir(month_index.parent)
  month_index.write_text(
    f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Issue {month}</title>
  <link rel="stylesheet" href="../../assets/qlu.css">
</head>
<body class="lang-en {body_class}">
  <main class="qlu-main {main_class}" style="width:min(100% - 1.25rem,46rem);margin:0 auto;padding:1rem 0 2rem">
    <p class="brand" style="color:var(--qlu-gold);font-size:.68rem;letter-spacing:.14em;text-transform:uppercase">Quantum Life University</p>
    <h1 style="color:var(--qlu-heading)">{month}</h1>
    <p><a href="te/index.html">తెలుగు · {label}</a> · <a href="en/index.html">English · {label}</a></p>
    <p><a href="../../index.html">All exports</a></p>
  </main>
</body>
</html>
""",
    encoding="utf-8",
  )
  catalog.write_text(
    f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QLU Magazine exports</title>
  <link rel="stylesheet" href="assets/qlu.css">
</head>
<body class="lang-en">
  <main class="qlu-main" style="width:min(100% - 1.25rem,46rem);margin:0 auto;padding:1rem 0 2rem">
    <p style="color:var(--qlu-gold);font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;font-weight:600">Quantum Life University</p>
    <h1 style="color:var(--qlu-heading)">Magazine exports</h1>
    <p style="color:var(--qlu-muted)">Astro {label} snapshots for GitHub Pages.</p>
    <ul>
      <li><a href="issues/{month}/te/index.html">{month} · TE · {label}</a></li>
      <li><a href="issues/{month}/en/index.html">{month} · EN · {label}</a></li>
      <li><a href="issues/{month}/index.html">{month} hub</a></li>
    </ul>
    <p><a href="../Tools/index.html">Newsletter Tools</a></p>
  </main>
</body>
</html>
""",
    encoding="utf-8",
  )
  print(f"  wrote catalog + month hub ({label})")


def run_snapshot(
  *,
  month: str,
  lang: str,
  astro: str,
  out: str,
  skip_stories: bool,
  view: str,
) -> int:
  if not re.fullmatch(r"\d{4}-\d{2}", month):
    raise SystemExit("--month must be YYYY-MM")
  if view not in ("news", "print"):
    raise SystemExit("--view must be news or print")

  docs = Path(out).resolve()
  assets = docs / "assets"
  ensure_dir(assets)
  (docs / ".nojekyll").write_text("", encoding="utf-8")

  write_qlu_css(assets / "qlu.css")
  write_client_js(assets)
  for name in ("qlu-logo.png", "favicon.svg", "newton-birthday.jpg"):
    copy_or_fetch_public(astro, name, assets / name)

  store = AssetStore(assets, astro)
  store.map["/qlu-logo.png"] = "qlu-logo.png"
  store.map["/favicon.svg"] = "favicon.svg"
  store.map["/newton-birthday.jpg"] = "newton-birthday.jpg"
  store.map["qlu.css"] = "qlu.css"
  store.map["newsview.js"] = "newsview.js"
  store.map["newsletterReel.js"] = "newsletterReel.js"
  store.map["card-masonry.js"] = "card-masonry.js"
  store.map["birthday-splash.js"] = "birthday-splash.js"

  media_dir = assets / "media"
  if media_dir.is_dir():
    for p in media_dir.iterdir():
      if p.is_file() and not re.search(
        r"\.(png|jpe?g|gif|webp|svg)$", p.name, re.I
      ):
        p.unlink(missing_ok=True)

  langs = LANGS if lang == "all" else (lang,)
  for L in langs:
    lang_root = docs / "issues" / month / L
    out_file = lang_root / "index.html"
    if view == "news":
      path = f"/issues/{month}/{L}/"
    else:
      path = f"/issues/{month}/{L}/?view=print"
    original = snapshot_page(
      astro=astro,
      path=path,
      out_file=out_file,
      store=store,
      docs_root=docs,
      lang_root=lang_root,
      month=month,
      lang=L,
      view=view,
    )
    if skip_stories:
      continue
    for section, item, story_path in extract_story_paths(original, month, L):
      story_out = lang_root / "story" / section / item / "index.html"
      from_view = "news" if view == "news" else "print"
      story_url_path = f"{story_path.rstrip('/')}/?from={from_view}"
      snapshot_page(
        astro=astro,
        path=story_url_path,
        out_file=story_out,
        store=store,
        docs_root=docs,
        lang_root=lang_root,
        month=month,
        lang=L,
        view=view,
      )

  write_catalog(docs, month, view=view)
  print(f"Done. Open {docs / 'issues' / month / 'te' / 'index.html'}")
  return 0


def main(argv: list[str] | None = None, *, default_view: str = "print") -> int:
  ap = argparse.ArgumentParser(
    description=f"Snapshot Astro {default_view.title()} view into docs/ for GitHub Pages",
  )
  ap.add_argument("--month", required=True, help="YYYY-MM")
  ap.add_argument(
    "--lang",
    choices=(*LANGS, "all"),
    default="all",
    help="Language to snapshot (default all)",
  )
  ap.add_argument(
    "--view",
    choices=("news", "print"),
    default=default_view,
    help=f"Astro view to snapshot (default {default_view})",
  )
  ap.add_argument("--astro", default=DEFAULT_ASTRO, help="Astro origin (default localhost:4321)")
  ap.add_argument("--out", default=str(REPO_ROOT / "docs"), help="docs root")
  ap.add_argument("--skip-stories", action="store_true", help="Do not snapshot Read more pages")
  args = ap.parse_args(argv)

  return run_snapshot(
    month=args.month,
    lang=args.lang,
    astro=args.astro,
    out=args.out,
    skip_stories=args.skip_stories,
    view=args.view,
  )


if __name__ == "__main__":
  sys.exit(main())
