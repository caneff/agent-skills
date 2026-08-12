/* checklist component */

function _ensure(block, selectors) {
  var blockClass =
    Array.from(block.classList).find(function (c) {
      return c.startsWith("vt-");
    }) || block.className;
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

function wireChecklist(list) {
  if (!_ensure(list, ['input[type="checkbox"]'])) return;

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
  barWrap.setAttribute("aria-label", "Checklist progress");
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

if (typeof document !== "undefined") {
  var _doWireChecklist = function () {
    document.querySelectorAll(".vt-checklist").forEach(function (el) {
      try {
        wireChecklist(el);
      } catch (e) {
        console.warn("visual-teach checklist: failed to wire", e);
      }
    });
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _doWireChecklist);
  } else {
    _doWireChecklist();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { wireChecklist: wireChecklist };
} else if (typeof window !== "undefined") {
  window.vtChecklist = { wireChecklist: wireChecklist };
}
