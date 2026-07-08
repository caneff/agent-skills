/* visual-teach — lesson behaviour. Auto-inits on DOMContentLoaded.
   Required children for each block are declared via the requires arrays in each
   wirer function; see wireQuiz / wireChecklist / wireCodeBlock below.
   Persistence keys off data-key; progress bar + count label + reset auto-injected. */

function announce(liveRegion, text) {
  if (liveRegion) liveRegion.textContent = text;
}

function blockLabel(el) {
  return (
    Array.from(el.classList).find(function (c) {
      return c.startsWith("vt-");
    }) || el.className
  );
}

// Check that block contains every required child selector. Warns for each
// missing one and returns false if any are absent so the wirer can bail out.
function ensure(block, selectors) {
  var blockClass = blockLabel(block);
  var ok = true;
  selectors.forEach(function (sel) {
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

// Feedback line: a verdict glyph (✔ / ✘) followed by the explanation HTML.
function verdict(ok, html) {
  return (
    '<span class="vt-fb-verdict">' +
    (ok ? "&#10004;" : "&#10008;") +
    "</span> " +
    html
  );
}

function wireQuiz(quiz) {
  // Optional: template.why-good, template.why-bad, template[data-opt="N"], [aria-live].
  if (!ensure(quiz, ["button.opt", ".feedback"])) return;

  var answers = quiz.dataset.answer
    ? quiz.dataset.answer.split(",").map(function (s) {
        return parseInt(s.trim(), 10);
      })
    : [0];

  var ctx = {
    quiz: quiz,
    opts: quiz.querySelectorAll("button.opt"),
    fb: quiz.querySelector(".feedback"),
    goodT: quiz.querySelector("template.why-good"),
    badT: quiz.querySelector("template.why-bad"),
    liveRegion: quiz.querySelector("[aria-live]"),
  };

  quiz.setAttribute("role", "group");
  ctx.opts.forEach(function (btn) {
    btn.setAttribute("type", "button");
  });

  if (quiz.hasAttribute("data-multi")) {
    var blockClass = blockLabel(quiz);
    if (!quiz.dataset.answer) {
      console.warn(
        "visual-teach: " +
          blockClass +
          " data-multi is missing data-answer — defaulting to index 0"
      );
    } else if (answers.length < 2) {
      console.warn(
        "visual-teach: " +
          blockClass +
          " data-multi has only one index in data-answer — did you mean to list multiple?"
      );
    }
    _wireMulti(ctx, answers);
  } else {
    _wireSingle(ctx, answers[0]);
  }
}

function _wireSingle(ctx, answer) {
  var quiz = ctx.quiz,
    opts = ctx.opts,
    fb = ctx.fb,
    goodT = ctx.goodT,
    badT = ctx.badT,
    liveRegion = ctx.liveRegion;
  // Single-answer never locks: a wrong pick shows feedback without revealing the
  // answer, and the learner keeps picking until correct. Buttons stay clickable
  // even after a correct pick, so they can browse the wrong-answer explanations.
  function reveal(chosen) {
    opts.forEach(function (b) {
      b.classList.remove("correct", "wrong");
    });

    var isCorrect = chosen === answer;
    if (isCorrect && opts[answer]) opts[answer].classList.add("correct");

    var whyGood = goodT ? goodT.innerHTML : "Correct.";

    if (isCorrect) {
      fb.className = "feedback show good";
      fb.innerHTML = verdict(true, whyGood);
      announce(liveRegion, fb.textContent);
    } else {
      var perOptT = quiz.querySelector('template[data-opt="' + chosen + '"]');
      var whyBad = perOptT
        ? perOptT.innerHTML
        : badT
          ? badT.innerHTML
          : "Not quite.";
      opts[chosen].classList.add("wrong");
      fb.className = "feedback show bad";
      fb.innerHTML = verdict(false, whyBad);
      announce(liveRegion, fb.textContent);
      // leave buttons enabled — learner keeps trying until correct.
    }
  }

  opts.forEach(function (btn, i) {
    btn.addEventListener("click", function () {
      reveal(i);
    });
  });
}

function _wireMulti(ctx, answers) {
  var opts = ctx.opts,
    fb = ctx.fb,
    goodT = ctx.goodT,
    badT = ctx.badT,
    liveRegion = ctx.liveRegion;
  var selected = new Set();

  opts.forEach(function (btn, i) {
    btn.setAttribute("aria-pressed", "false");
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      var pressed = selected.has(i);
      if (pressed) {
        selected.delete(i);
        btn.setAttribute("aria-pressed", "false");
        btn.classList.remove("selected");
      } else {
        selected.add(i);
        btn.setAttribute("aria-pressed", "true");
        btn.classList.add("selected");
      }
    });
  });

  var checkBtn = document.createElement("button");
  checkBtn.type = "button";
  checkBtn.className = "vt-quiz-check";
  checkBtn.textContent = "Check answer";
  fb.parentNode.insertBefore(checkBtn, fb);

  checkBtn.addEventListener("click", function () {
    var allCorrect =
      answers.every(function (a) {
        return selected.has(a);
      }) &&
      Array.from(selected).every(function (s) {
        return answers.indexOf(s) !== -1;
      });

    opts.forEach(function (btn, i) {
      btn.classList.remove("correct", "wrong", "selected");
      btn.setAttribute("aria-pressed", "false");
      var isAnswer = answers.indexOf(i) !== -1;
      if (selected.has(i)) {
        btn.classList.add(isAnswer ? "correct" : "wrong");
      } else if (isAnswer) {
        btn.classList.add("correct");
      }
      btn.disabled = true;
    });

    var whyGood = goodT ? goodT.innerHTML : "Correct.";
    if (allCorrect) {
      fb.className = "feedback show good";
      fb.innerHTML = verdict(true, whyGood);
    } else {
      fb.className = "feedback show bad";
      fb.innerHTML =
        verdict(false, badT ? badT.innerHTML : "Not quite.") +
        '<div class="vt-fb-correct">' +
        verdict(true, whyGood) +
        "</div>";
    }
    announce(liveRegion, fb.textContent);
    checkBtn.remove();
  });
}

function wireChecklist(list) {
  if (!ensure(list, ['input[type="checkbox"]'])) return;

  var key = "vt-checklist:" + (list.dataset.key || location.pathname);
  var boxes = list.querySelectorAll('input[type="checkbox"]');
  var total = boxes.length;

  boxes.forEach(function (b, i) {
    if (!b.dataset.i) b.dataset.i = String(i);
    if (!b.id) b.id = "vt-cl-" + (list.dataset.key || "x") + "-" + i;
    if (!b.labels || b.labels.length === 0) {
      var lbl = document.createElement("label");
      lbl.setAttribute("for", b.id);
      var sibling = b.nextElementSibling;
      if (sibling && sibling.tagName !== "LABEL") {
        lbl.appendChild(sibling);
      }
      b.parentNode.insertBefore(lbl, b.nextSibling);
    }
  });

  var saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(key) || "{}");
  } catch (e) {}

  var barWrap = document.createElement("div");
  barWrap.className = "vt-progress-bar";
  barWrap.setAttribute("role", "progressbar");
  barWrap.setAttribute("aria-valuemin", "0");
  barWrap.setAttribute("aria-valuemax", "100");
  barWrap.setAttribute("aria-valuenow", "0");

  var barFill = document.createElement("div");
  barFill.className = "vt-progress-bar-fill";
  barFill.style.width = "0%";
  barWrap.appendChild(barFill);

  var progress = document.createElement("p");
  progress.className = "vt-progress";

  var reset = document.createElement("button");
  reset.className = "vt-reset";
  reset.type = "button";
  reset.textContent = "Reset";

  // count label + compact reset share one row above the bar
  var head = document.createElement("div");
  head.className = "vt-progress-head";
  head.appendChild(progress);
  head.appendChild(reset);

  list.parentNode.insertBefore(head, list);
  list.parentNode.insertBefore(barWrap, list);

  function render() {
    var done = 0;
    boxes.forEach(function (b) {
      if (b.checked) done++;
    });
    var pct = total > 0 ? Math.round((done / total) * 100) : 0;
    barFill.style.width = pct + "%";
    barWrap.setAttribute("aria-valuenow", String(pct));
    progress.textContent =
      done === total
        ? "✅ All " + total + " steps done."
        : done + " of " + total + " steps done";
  }

  function save() {
    try {
      localStorage.setItem(key, JSON.stringify(saved));
    } catch (e) {}
  }

  boxes.forEach(function (b) {
    b.checked = !!saved[b.dataset.i];
    b.addEventListener("change", function () {
      saved[b.dataset.i] = b.checked;
      save();
      render();
    });
  });

  reset.addEventListener("click", function () {
    boxes.forEach(function (b) {
      b.checked = false;
      saved[b.dataset.i] = false;
    });
    save();
    render();
  });

  render();
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
  if (!ensure(block, ["pre"])) return;
  if (block.classList.contains("vt-static")) return;
  if (!ensure(block, [".vt-code-copy"])) return;
  wireCopyButton(block);
}

function wireIO(block) {
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
          ".min.js before visual-teach.js."
      );
    }
  });
  try {
    Prism.highlightAll();
  } catch (e) {}
}

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

/* Standalone theme toggle: inject a fixed dark/light switch for a learner
   opening a lesson on its own. Skipped when (a) the page already has a
   .vt-theme-toggle (hand-built demos) or (b) the page is iframed — there the
   embedding parent owns the theme via postMessage (wireThemeBridge). */
function wireThemeToggle(win) {
  var doc = win.document;
  if (doc.querySelector(".vt-theme-toggle")) return;
  try {
    if (win.self !== win.top) return;
  } catch (e) {
    return;
  } // iframed → parent owns theme
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

/* KaTeX math rendering: processes .vt-math display blocks and inline math
   delimiters (\(...\) and \[...\]) in the document body.
   Silently skips when katex global is absent (no network, no KaTeX loaded). */
function initKatex() {
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
        throwOnError: false,
      });
    } catch (e) {
      // leave inline math as-is on failure
    }
  }
}

var BLOCKS = [
  { sel: ".vt-quiz", wire: wireQuiz },
  { sel: ".vt-checklist", wire: wireChecklist },
  { sel: ".vt-code", wire: wireCodeBlock },
  { sel: ".vt-io", wire: wireIO },
];

function wireBlocks() {
  BLOCKS.forEach(function (b) {
    document.querySelectorAll(b.sel).forEach(function (el) {
      try {
        b.wire(el);
      } catch (e) {
        console.warn(
          "visual-teach: " + b.sel + " failed to wire, left inert",
          e
        );
      }
    });
  });
}

// Detect visual row breaks in a .vt-flow and mark the first item on each
// wrapped row with vt-row-start so CSS can suppress the leading → arrow.
function markFlowRows(flow) {
  var children = Array.from(flow.children);
  children.forEach(function (child) {
    child.classList.remove("vt-row-start");
  });
  if (children.length === 0) return;
  var rowBottom = children[0].offsetTop + children[0].offsetHeight;
  for (var i = 1; i < children.length; i++) {
    var child = children[i];
    if (child.offsetTop >= rowBottom) {
      child.classList.add("vt-row-start");
    }
    rowBottom = Math.max(rowBottom, child.offsetTop + child.offsetHeight);
  }
}

function initFlows() {
  var flows = document.querySelectorAll(".vt-flow");
  flows.forEach(function (flow) {
    markFlowRows(flow);
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(function () {
        markFlowRows(flow);
      }).observe(flow);
    }
  });
}

function init() {
  // Each step runs isolated — one failing step never blocks the rest.
  [
    wireBlocks,
    wireAnchors,
    initPrism,
    initKatex,
    initFlows,
    function () {
      if (typeof window !== "undefined") {
        wireThemeBridge(window);
        wireThemeToggle(window);
      }
    },
  ].forEach(function (step) {
    try {
      step();
    } catch (e) {
      console.warn("visual-teach: init step failed", e);
    }
  });
}

// UMD: expose the public API for tests (CommonJS) and as a browser global.
// Plain-script export (no ESM `export`) lets lessons load this with a classic
// <script src> that works from file:// — no module CORS, no local server.
var vtVisualTeach = {
  wireQuiz: wireQuiz,
  wireChecklist: wireChecklist,
  wireThemeBridge: wireThemeBridge,
  wireThemeToggle: wireThemeToggle,
  markFlowRows: markFlowRows,
  initFlows: initFlows,
  BLOCKS: BLOCKS,
  init: init,
};
if (typeof module !== "undefined" && module.exports) {
  module.exports = vtVisualTeach;
} else if (typeof window !== "undefined") {
  window.vtVisualTeach = vtVisualTeach;
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}
