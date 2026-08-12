/* visual-teach — diagram component.
   Handles .vt-flow row-break detection and ResizeObserver updates. */

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

if (typeof document !== "undefined") {
  var _doInitFlows = function () {
    initFlows();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _doInitFlows);
  } else {
    _doInitFlows();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { markFlowRows: markFlowRows, initFlows: initFlows };
} else if (typeof window !== "undefined") {
  window.vtDiagram = { markFlowRows: markFlowRows, initFlows: initFlows };
}
