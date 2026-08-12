/* visual-teach — opt-in mermaid bridge.
   Lazy-loads mermaid only when .vt-mermaid elements are present, preferring the
   vendored mermaid.min.js sitting beside this file so diagrams render offline
   over file://; the CDN is only a fallback if that local copy fails to load.
   Include this file in lessons that use computed graphs (sequence, state, ER);
   prefer the hand-composed CSS diagram vocabulary for everything else.

   Browser auto-init fires on DOMContentLoaded (or immediately if already loaded).
   In CommonJS/Node (tests) the factory is exported directly without auto-init.

   Usage:
     <div class="vt-mermaid">
       sequenceDiagram
         A->>B: Hello
     </div>
     <script src="../assets/mermaid.js"></script>
*/
(function (root, factory) {
  "use strict";
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory();
  } else {
    root.vtMermaid = factory();
    if (typeof document !== "undefined") {
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
          root.vtMermaid.init();
        });
      } else {
        root.vtMermaid.init();
      }
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js";

  // Where this script was served from, captured now (document.currentScript is
  // null once we're inside init on DOMContentLoaded). The vendored mermaid.min.js
  // sits beside it, so swapping the filename gives a path that resolves over
  // file:// no matter where the page itself lives.
  var SELF =
    (typeof document !== "undefined" &&
      document.currentScript &&
      document.currentScript.src) ||
    "";

  function siblingMin(self) {
    return self ? self.replace(/[^/]*$/, "mermaid.min.js") : "";
  }

  // mermaid.initialize() config, brand-blue tint both sides. We use mermaid's
  // native 'base'/'dark' themes (coherent, tested palettes) rather than hand-
  // mapping vt-* tokens onto 'base' — that produced a monochromatic look and
  // white-on-white state-node labels. labelBg matches the card the diagram sits
  // on; see bgBehind().
  function darkTheme(labelBg) {
    // dark theme ignores primaryColor for node fills, so set mainBkg/secondary/
    // tertiary too. One light-grey token (tx) pins every text element: mermaid
    // pulls node text, titles, edge/transition labels, sequence actors/messages,
    // and class members from separate vars; left unset they fall back to the
    // dark theme's mix of white + grey.
    var tx = "#e6e9ef";
    return {
      startOnLoad: false,
      theme: "dark",
      themeVariables: {
        darkMode: true,
        primaryColor: "#1e3a5f",
        mainBkg: "#1e3a5f",
        secondaryColor: "#1e3a5f",
        tertiaryColor: "#1e3a5f",
        // ER attribute rows: neutral grey (blue header only), mirroring light's
        // blue-header / white-rows. Same odd+even = no stripe.
        rowOdd: "#2b313b",
        rowEven: "#2b313b",
        primaryTextColor: tx,
        secondaryTextColor: tx,
        tertiaryTextColor: tx,
        textColor: tx,
        nodeTextColor: tx,
        titleColor: tx,
        classText: tx,
        actorTextColor: tx,
        signalTextColor: tx,
        labelTextColor: tx,
        loopTextColor: tx,
        edgeLabelBackground: labelBg,
      },
    };
  }

  function lightTheme(labelBg) {
    return {
      startOnLoad: false,
      theme: "base",
      themeVariables: { primaryColor: "#dbe9ff", edgeLabelBackground: labelBg },
    };
  }

  // Walk up from a node to the first element with a non-transparent background.
  // Used to match mermaid's edge-label boxes to the card the diagram sits on.
  function bgBehind(node, gcs) {
    gcs =
      gcs ||
      (typeof window !== "undefined"
        ? window.getComputedStyle.bind(window)
        : null);
    if (!gcs || !node) return null;
    for (var el = node; el; el = el.parentElement) {
      var c = gcs(el).backgroundColor;
      if (c && c !== "transparent" && c !== "rgba(0, 0, 0, 0)") return toRgb(c);
    }
    return null;
  }

  // Normalize any CSS color (incl. color-mix's color(srgb ...) form) to plain
  // rgb()/hex via canvas — mermaid's color lib throws on the color(srgb ...)
  // syntax, which breaks flowchart rendering.
  function toRgb(c) {
    if (typeof document === "undefined") return c;
    var cv = document.createElement("canvas");
    cv.width = cv.height = 1;
    var ctx = cv.getContext("2d");
    if (!ctx) return c;
    ctx.fillStyle = c;
    ctx.fillRect(0, 0, 1, 1);
    var d = ctx.getImageData(0, 0, 1, 1).data;
    return d[3] === 255
      ? "rgb(" + d[0] + "," + d[1] + "," + d[2] + ")"
      : "rgba(" + d[0] + "," + d[1] + "," + d[2] + "," + d[3] / 255 + ")";
  }

  // Detect dark mode from [data-theme] attribute, falling back to matchMedia.
  function isDark(docEl, mm) {
    var t = docEl.dataset && docEl.dataset.theme;
    if (t === "dark") return true;
    if (t === "light") return false;
    var mq =
      mm ||
      (typeof window !== "undefined" && window.matchMedia
        ? window.matchMedia.bind(window)
        : null);
    return !!(mq && mq("(prefers-color-scheme: dark)").matches);
  }

  // No-ops when no .vt-mermaid elements are found — zero CDN cost for lessons
  // that don't use computed graphs.
  function init(doc, options) {
    doc = doc || (typeof document !== "undefined" ? document : null);
    if (!doc) return;
    var nodes = doc.querySelectorAll(".vt-mermaid");
    if (!nodes.length) return;

    options = options || {};
    // Prefer the vendored sibling; fall back to the CDN only when we can't
    // derive a local path. options.cdn forces an exact URL (used by tests).
    var src = options.cdn || siblingMin(options.self || SELF) || CDN;

    var list = Array.from(nodes);
    // Stash each diagram's source now; mermaid.run() replaces it with SVG, so we
    // need the original text to re-render when the theme flips.
    var sources = list.map(function (n) {
      return n.textContent;
    });

    function render() {
      var dark = isDark(doc.documentElement, options.matchMedia);
      list.forEach(function (n, i) {
        n.removeAttribute("data-processed");
        n.innerHTML = sources[i];
      });
      // Match the edge/transition-label background to whatever the diagram
      // actually sits on (a card, not necessarily --vt-paper), so labels never
      // get a muddy mismatched box. Read it live rather than hardcode.
      var labelBg =
        bgBehind(list[0], options.getComputedStyle) ||
        (dark ? "#13171d" : "#ffffff");
      // mermaid paints .labelBkg at 50% alpha (a baked-in CSS rule, no themeVar
      // for it) — over an ER relationship line that leaves the line showing
      // through and a faint tint. Force it opaque and card-matched.
      var styleEl = doc.getElementById("vt-mermaid-style");
      if (!styleEl) {
        styleEl = doc.createElement("style");
        styleEl.id = "vt-mermaid-style";
        doc.head.appendChild(styleEl);
      }
      styleEl.textContent =
        ".vt-mermaid .labelBkg{background-color:" + labelBg + " !important}";
      window.mermaid.initialize(
        dark ? darkTheme(labelBg) : lightTheme(labelBg)
      );
      window.mermaid.run({ nodes: list });
    }

    var script = doc.createElement("script");
    function onLoad() {
      render();
      // Re-render on data-theme toggle so diagrams follow the page palette.
      if (typeof MutationObserver !== "undefined") {
        new MutationObserver(render).observe(doc.documentElement, {
          attributes: true,
          attributeFilter: ["data-theme"],
        });
      }
    }

    script.src = src;
    script.onload = onLoad;
    // If the vendored copy is missing (e.g. a stale downstream sync), retry once
    // over the CDN so online readers still get diagrams.
    script.onerror = function () {
      if (src === CDN) return;
      var fb = doc.createElement("script");
      fb.src = CDN;
      fb.onload = onLoad;
      doc.head.appendChild(fb);
    };
    doc.head.appendChild(script);
  }

  return { init: init, isDark: isDark };
});
