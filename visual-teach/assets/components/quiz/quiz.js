/* quiz component */

function _announce(r, t) {
  if (r) r.textContent = t;
}

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

function _verdict(ok, html) {
  return (
    '<span class="vt-fb-verdict">' +
    (ok ? "&#10004;" : "&#10008;") +
    "</span> " +
    html
  );
}

function wireQuiz(quiz) {
  // Optional: template.why-good, template.why-bad, template[data-opt="N"], [aria-live].
  if (!_ensure(quiz, ["button.opt", ".feedback"])) return;

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
    var blockClass =
      Array.from(quiz.classList).find(function (c) {
        return c.startsWith("vt-");
      }) || quiz.className;
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
      fb.innerHTML = _verdict(true, whyGood);
      _announce(liveRegion, fb.textContent);
    } else {
      var perOptT = quiz.querySelector('template[data-opt="' + chosen + '"]');
      var whyBad = perOptT
        ? perOptT.innerHTML
        : badT
          ? badT.innerHTML
          : "Not quite.";
      opts[chosen].classList.add("wrong");
      fb.className = "feedback show bad";
      fb.innerHTML = _verdict(false, whyBad);
      _announce(liveRegion, fb.textContent);
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
      fb.innerHTML = _verdict(true, whyGood);
    } else {
      fb.className = "feedback show bad";
      fb.innerHTML =
        _verdict(false, badT ? badT.innerHTML : "Not quite.") +
        '<div class="vt-fb-correct">' +
        _verdict(true, whyGood) +
        "</div>";
    }
    _announce(liveRegion, fb.textContent);
    checkBtn.remove();
  });
}

if (typeof document !== "undefined") {
  var _doWireQuiz = function () {
    document.querySelectorAll(".vt-quiz").forEach(function (el) {
      try {
        wireQuiz(el);
      } catch (e) {
        console.warn("visual-teach quiz: failed to wire", e);
      }
    });
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _doWireQuiz);
  } else {
    _doWireQuiz();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { wireQuiz: wireQuiz };
} else if (typeof window !== "undefined") {
  window.vtQuiz = { wireQuiz: wireQuiz };
}
