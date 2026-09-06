(function () {
  var DEBOUNCE_MS = 300;

  var ensure = (typeof window !== "undefined" && window.vtBase && window.vtBase.ensure) || function () { return true; };

  function wireSandbox(sandbox) {
    var blockClass =
      Array.from(sandbox.classList).find(function (c) {
        return c.startsWith("vt-");
      }) || sandbox.className;

    if (!ensure(sandbox, ["input, textarea", ".vt-sandbox-output"])) return;

    if (!sandbox.dataset.fn) {
      console.warn(
        "visual-teach: " +
          blockClass +
          " missing required data-fn attribute — left inert"
      );
      return;
    }

    var fn = window[sandbox.dataset.fn];
    if (typeof fn !== "function") {
      console.warn(
        "visual-teach: " +
          blockClass +
          ' data-fn="' +
          sandbox.dataset.fn +
          '" is not a function in window — left inert'
      );
      return;
    }

    var field = sandbox.querySelector("input, textarea");
    var output = sandbox.querySelector(".vt-sandbox-output");
    var timer = null;

    function getOrCreateError() {
      var err = sandbox.querySelector(".vt-sandbox-error");
      if (!err) {
        err = document.createElement("div");
        err.className = "vt-sandbox-error";
        err.setAttribute("aria-live", "polite");
        output.parentNode.insertBefore(err, output.nextSibling);
      }
      return err;
    }

    function evaluate() {
      try {
        var result = fn(field.value);
        output.textContent = result == null ? "" : String(result);
        var err = sandbox.querySelector(".vt-sandbox-error");
        if (err) err.textContent = "";
      } catch (e) {
        getOrCreateError().textContent = e && e.message ? e.message : String(e);
      }
    }

    field.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(evaluate, DEBOUNCE_MS);
    });
  }

  if (typeof window !== "undefined" && window.vtBase) {
    window.vtBase.register(".vt-sandbox", wireSandbox, "sandbox");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { wireSandbox: wireSandbox };
  } else if (typeof window !== "undefined") {
    window.vtSandbox = { wireSandbox: wireSandbox };
  }
})();
