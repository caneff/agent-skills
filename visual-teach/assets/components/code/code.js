(function () {
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
    var ensure = window.vtBase.ensure;
    if (!ensure(block, ["pre"])) return;
    if (block.classList.contains("vt-static")) return;
    if (!ensure(block, [".vt-code-copy"])) return;
    wireCopyButton(block);
  }

  function wireIO(block) {
    var ensure = window.vtBase.ensure;
    if (!ensure(block, [".vt-io-input", ".vt-io-output"])) return;
    var input = block.querySelector(".vt-io-input");
    if (!ensure(input, [".vt-code-copy", "pre"])) return;
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

  if (typeof window !== "undefined" && window.vtBase) {
    window.vtBase.register(".vt-code", wireCodeBlock, "code");
    window.vtBase.register(".vt-io", wireIO, "io");
    window.vtBase.register(null, initPrism, "prism");
  } else if (typeof window !== "undefined") {
    console.warn(
      "visual-teach: code.js loaded without visual-teach base.js — not wired"
    );
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
})();
