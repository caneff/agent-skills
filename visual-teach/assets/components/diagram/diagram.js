(function () {
  // Mark the first item on each wrapped row with vt-row-start so CSS can
  // suppress the leading → arrow.
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

  function wireFlow(flow) {
    markFlowRows(flow);
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(function () {
        markFlowRows(flow);
      }).observe(flow);
    }
  }

  if (typeof window !== "undefined" && window.vtBase) {
    window.vtBase.register(".vt-flow", wireFlow, "diagram");
  } else if (typeof window !== "undefined") {
    console.warn(
      "visual-teach: diagram.js loaded without visual-teach base.js — not wired"
    );
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { markFlowRows: markFlowRows, wireFlow: wireFlow };
  } else if (typeof window !== "undefined") {
    window.vtDiagram = { markFlowRows: markFlowRows, wireFlow: wireFlow };
  }
})();
