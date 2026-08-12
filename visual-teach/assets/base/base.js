/* base — the always-linked spine: theme bridge/toggle, section anchors, init.
   Block-level helpers (announce/ensure/verdict) and component behaviour (quiz,
   checklist, code, Prism, KaTeX, diagrams) each live in their own component
   file — every Component is self-contained so it can be copied on its own. */

/* Theme bridge: let an embedding parent (e.g. an iframe-based before/after
   compare page) set the lesson theme via postMessage({vtTheme:'dark'|'light'}).
   Cross-origin-safe, so it works even when lessons are opened over file://,
   where the parent cannot reach contentDocument. */
function wireThemeBridge(win) {
  win.addEventListener("message", function (e) {
    var t = e.data && e.data.vtTheme;
    if (t === "dark" || t === "light")
      win.document.documentElement.dataset.theme = t;
  });
}

/* Standalone theme toggle: inject a fixed dark/light switch. Rendered whether
   the lesson is opened directly or embedded in an iframe (e.g. a before/after
   compare page), so the reader gets the same native control either way. Skipped
   only when the page already ships its own .vt-theme-toggle. The postMessage
   bridge (wireThemeBridge) stays available for a parent that prefers to drive
   the theme programmatically instead. */
function wireThemeToggle(win) {
  var doc = win.document;
  if (doc.querySelector(".vt-theme-toggle")) return;
  var stored = null;
  try {
    stored = win.localStorage.getItem("vtTheme");
  } catch (e) {}
  if (stored === "dark" || stored === "light")
    doc.documentElement.dataset.theme = stored;
  var btn = doc.createElement("button");
  btn.className = "vt-theme-toggle";
  btn.type = "button";
  btn.textContent = "◐ theme";
  btn.setAttribute("aria-label", "Toggle dark or light theme");
  btn.style.cssText =
    "position:fixed;top:1rem;right:1rem;z-index:99;font:inherit;font-size:.8rem;" +
    "padding:.35rem .7rem;border-radius:999px;cursor:pointer;border:1px solid var(--vt-rule);" +
    "background:var(--vt-soft);color:var(--vt-ink);";
  btn.addEventListener("click", function () {
    var dark =
      doc.documentElement.dataset.theme === "dark" ||
      (!doc.documentElement.dataset.theme &&
        win.matchMedia("(prefers-color-scheme: dark)").matches);
    var next = dark ? "light" : "dark";
    doc.documentElement.dataset.theme = next;
    try {
      win.localStorage.setItem("vtTheme", next);
    } catch (e) {}
  });
  doc.body.appendChild(btn);
}

function slugify(s) {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

/* Make every section heading linkable: slug -> id, inject a hover "#" anchor.
   Skips headings that already carry an anchor (hand-authored demos). */
function wireAnchors() {
  var seen = {};
  document.querySelectorAll("h2, h3").forEach(function (h) {
    if (h.querySelector(".vt-anchor")) return;
    var clone = h.cloneNode(true);
    clone
      .querySelectorAll(".vt-num, .sc-sub, .vt-anchor")
      .forEach(function (n) {
        n.remove();
      });
    var base = slugify(clone.textContent || "");
    if (!base) return;
    var slug = h.id || base,
      n = 1;
    while (!h.id && seen[slug]) {
      n++;
      slug = base + "-" + n;
    }
    seen[slug] = true;
    if (!h.id) h.id = slug;
    var a = document.createElement("a");
    a.className = "vt-anchor";
    a.href = "#" + h.id;
    a.setAttribute("aria-label", "Link to this section");
    a.textContent = "#";
    h.appendChild(a);
  });
}

/* For each candidate block in <main> (table-wrap, code, diagram), measure its
   natural (max-content) width via an off-screen clone — SVG max-width is lifted
   on the clone so a wide SVG is not falsely capped to the column. Toggle
   .vt-wide when the natural width exceeds the column width at rest. */
function wireBreakout() {
  var doc = document;
  var main = doc.querySelector("main");
  if (!main) return;

  function applyBreakout() {
    var candidates = main.querySelectorAll(
      ".vt-table-wrap, .vt-code, .vt-diagram"
    );
    if (!candidates.length) return;

    // Strip any stale .vt-wide so getBoundingClientRect gives the at-rest column width.
    candidates.forEach(function (el) {
      el.classList.remove("vt-wide");
    });

    // All candidates share the same prose column — measure once.
    var columnWidth = candidates[0].getBoundingClientRect().width;

    candidates.forEach(function (el) {
      var clone = el.cloneNode(true);
      clone.style.cssText =
        "position:absolute;top:-9999px;left:-9999px;" +
        "width:max-content;max-width:none;visibility:hidden;";
      // Lift svg max-width so a wide SVG is not capped by the column CSS rule.
      clone.querySelectorAll("svg").forEach(function (svg) {
        svg.style.maxWidth = "none";
      });
      doc.body.appendChild(clone);
      var naturalWidth = clone.scrollWidth;
      doc.body.removeChild(clone);

      el.classList.toggle("vt-wide", naturalWidth > columnWidth);
    });
  }

  applyBreakout();

  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(applyBreakout, 150);
  });
}

function init() {
  wireAnchors();
  if (typeof window !== "undefined") {
    wireThemeBridge(window);
    wireThemeToggle(window);
    wireBreakout();
  }
}

// UMD: expose the public API for tests (CommonJS) and as a browser global.
// Plain-script export (no ESM `export`) lets lessons load this with a classic
// <script src> that works from file:// — no module CORS, no local server.
var vtBase = {
  wireThemeBridge: wireThemeBridge,
  wireThemeToggle: wireThemeToggle,
  wireAnchors: wireAnchors,
  wireBreakout: wireBreakout,
  init: init,
};
if (typeof module !== "undefined" && module.exports) {
  module.exports = vtBase;
} else if (typeof window !== "undefined") {
  window.vtBase = vtBase;
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}
