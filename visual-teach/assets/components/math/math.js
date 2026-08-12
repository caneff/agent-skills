/* visual-teach — math component.
   Renders .vt-math display blocks and inline \(...\) / \[...\] delimiters
   via KaTeX. Owns its own KaTeX dependency: if the katex global is absent,
   it injects katex.min.css + katex.min.js + auto-render.min.js (in order)
   from the assets/katex/ dir next to this component, then renders.
   Consumers only need to include math.js — no KaTeX wiring required. */

/* Resolve assets/ base from this script's own URL while currentScript is
   still valid (it's null inside the async callbacks below). */
var _vtMathBase = (function () {
  var s = typeof document !== "undefined" && document.currentScript;
  var src = (s && s.src) || "";
  return src.replace(/components\/math\/math\.js(\?.*)?$/, "");
})();

/* KaTeX math rendering: processes .vt-math display blocks and inline math
   delimiters (\(...\) and \[...\]) in the document body. */
function renderKatex() {
  if (typeof katex === "undefined") return;

  document.querySelectorAll(".vt-math").forEach(function (el) {
    var tex = el.textContent.trim();
    try {
      el.innerHTML = katex.renderToString(tex, {
        displayMode: true,
        throwOnError: false,
      });
    } catch (e) {
      // leave raw text intact on parse error
    }
  });

  if (typeof renderMathInElement === "function") {
    try {
      renderMathInElement(document.body, {
        delimiters: [
          { left: "\\(", right: "\\)", display: false },
          { left: "\\[", right: "\\]", display: true },
        ],
        // katex: skip already-rendered output; vt-math: renderToString owns those
        ignoredClasses: ["katex", "vt-math"],
        throwOnError: false,
      });
    } catch (e) {
      // leave inline math as-is on failure
    }
  }
}

/* Load a script once, resolving when ready. Reuses an existing tag if a
   consumer already included it (idempotent — safe to double-wire). */
function _loadScript(src) {
  return new Promise(function (resolve) {
    var existing = document.querySelector('script[src="' + src + '"]');
    if (existing) {
      if (existing.dataset.vtLoaded) return resolve();
      return existing.addEventListener("load", function () {
        resolve();
      });
    }
    var el = document.createElement("script");
    el.src = src;
    el.addEventListener("load", function () {
      el.dataset.vtLoaded = "1";
      resolve();
    });
    el.addEventListener("error", function () {
      resolve();
    }); // renderKatex() no-ops if katex never loaded
    document.head.appendChild(el);
  });
}

/* Ensure KaTeX + auto-render are present, injecting them if needed. */
function ensureKatex() {
  if (typeof katex !== "undefined") return Promise.resolve();
  var katexBase = _vtMathBase + "katex/";

  if (!document.querySelector('link[href="' + katexBase + 'katex.min.css"]')) {
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = katexBase + "katex.min.css";
    // Insert at head START: katex.min.css sets .katex{font:…1.21em…} at the
    // same specificity as math.css's 1em reset — the reset only wins if the
    // KaTeX sheet loads first. Appending it last silently oversizes all math.
    document.head.insertBefore(link, document.head.firstChild);
  }

  return _loadScript(katexBase + "katex.min.js").then(function () {
    return _loadScript(katexBase + "auto-render.min.js");
  });
}

function initKatex() {
  if (typeof katex !== "undefined") {
    renderKatex(); // already loaded — render synchronously
    return;
  }
  ensureKatex().then(renderKatex);
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initKatex);
  } else {
    initKatex();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { initKatex: initKatex, renderKatex: renderKatex };
} else if (typeof window !== "undefined") {
  window.vtMath = { initKatex: initKatex, renderKatex: renderKatex };
}
