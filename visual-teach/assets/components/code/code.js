/* visual-teach — code component.
   Handles .vt-code blocks (with copy button), .vt-io paired input→output blocks,
   and Prism syntax highlighting initialisation. */

function _ensure(block, sels) {
  var blockClass =
    Array.from(block.classList).find(function (c) {
      return c.startsWith("vt-");
    }) || block.className;
  var ok = true;
  sels.forEach(function (sel) {
    if (!block.querySelector(sel)) {
      console.warn(
        "visual-teach: " +
          blockClass +
          " missing required " +
          sel +
          " — left inert"
      );
      ok = false;
    }
  });
  return ok;
}

var COPY_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
var CHECK_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';

function wireCopyButton(container) {
  var btn = container.querySelector(".vt-code-copy");
  var pre = container.querySelector("pre");
  btn.innerHTML = COPY_ICON;
  if (!btn.getAttribute("aria-label"))
    btn.setAttribute("aria-label", "Copy code");
  btn.addEventListener("click", function () {
    var text = pre.textContent || "";
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(function () {
          btn.innerHTML = CHECK_ICON;
          setTimeout(function () {
            btn.innerHTML = COPY_ICON;
          }, 2000);
        })
        .catch(function () {});
    }
  });
}

function wireCodeBlock(block) {
  if (!_ensure(block, ["pre"])) return;
  if (block.classList.contains("vt-static")) return;
  if (!_ensure(block, [".vt-code-copy"])) return;
  wireCopyButton(block);
}

function wireIO(block) {
  if (!_ensure(block, [".vt-io-input", ".vt-io-output"])) return;
  var input = block.querySelector(".vt-io-input");
  if (!_ensure(input, [".vt-code-copy", "pre"])) return;
  wireCopyButton(input);
}

function initPrism() {
  if (typeof Prism === "undefined") return;
  var blocks = document.querySelectorAll(
    '.vt-code code[class*="language-"], .vt-io-input code[class*="language-"]'
  );
  if (!blocks.length) return;
  blocks.forEach(function (el) {
    var langClass = Array.from(el.classList).find(function (cls) {
      return cls.startsWith("language-");
    });
    var lang = langClass ? langClass.slice("language-".length) : null;
    if (lang && Prism.languages && !Prism.languages[lang]) {
      console.warn(
        "visual-teach: no Prism grammar loaded for language-" +
          lang +
          ". Add prism-" +
          lang +
          ".min.js before code.js."
      );
    }
  });
  try {
    Prism.highlightAll();
  } catch (e) {}
}

if (typeof document !== "undefined") {
  var _doWireCode = function () {
    document.querySelectorAll(".vt-code").forEach(function (el) {
      try {
        wireCodeBlock(el);
      } catch (e) {
        console.warn("visual-teach code: failed", e);
      }
    });
    document.querySelectorAll(".vt-io").forEach(function (el) {
      try {
        wireIO(el);
      } catch (e) {
        console.warn("visual-teach io: failed", e);
      }
    });
    initPrism();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _doWireCode);
  } else {
    _doWireCode();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    wireCopyButton: wireCopyButton,
    wireCodeBlock: wireCodeBlock,
    wireIO: wireIO,
    initPrism: initPrism,
  };
} else if (typeof window !== "undefined") {
  window.vtCode = {
    wireCopyButton: wireCopyButton,
    wireCodeBlock: wireCodeBlock,
    wireIO: wireIO,
    initPrism: initPrism,
  };
}
