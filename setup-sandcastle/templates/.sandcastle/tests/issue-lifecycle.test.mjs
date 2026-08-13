import { test, expect, describe } from "vitest";
import {
  planOutcomeTransition,
  planFailureBodyEdit,
  spliceReviewFailureSection,
  REVIEW_FAILURE_BEGIN,
  REVIEW_FAILURE_END,
} from "../issue-lifecycle.mts";

describe("planOutcomeTransition", () => {
  const full = {
    id: "42",
    title: "Add widget",
    branch: "sandcastle/issue-42",
    parents: ["7"],
    group: "widgets",
  };

  test("done → in-review, dropping the buildable label; branch not preserved", () => {
    const plan = planOutcomeTransition({ kind: "done", issue: full });
    expect(plan.addLabel).toBe("in-review");
    expect(plan.removeLabels).toEqual(["ready-for-agent"]);
    expect(plan.preserveBranch).toBe(false);
    expect(plan.failureSection).toBeUndefined();
  });

  test("review-fail → ready-for-human, branch preserved, no PR path", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["spec"],
    });
    expect(plan.addLabel).toBe("ready-for-human");
    expect(plan.removeLabels).toEqual(["ready-for-agent"]);
    expect(plan.preserveBranch).toBe(true);
    expect(plan.completed).toBeUndefined();
    expect(plan.note).toBe(
      "42 failed review (spec); no PR — branch preserved, handed to a human (ready-for-human)"
    );
  });

  test("a standards-only failure names standards, not spec", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["standards"],
    });
    expect(plan.note).toContain("failed review (standards)");
    expect(plan.failureSection).toContain("**standards**");
  });

  test("both axes failing names both, in the note and the section", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["spec", "standards"],
    });
    expect(plan.note).toContain("failed review (spec, standards)");
    expect(plan.failureSection).toContain("**spec**");
    expect(plan.failureSection).toContain("**standards**");
  });

  test("no axes given → reads as 'review' rather than an empty bracket", () => {
    const plan = planOutcomeTransition({ kind: "review-fail", issue: full });
    expect(plan.note).toContain("failed review (review)");
    expect(plan.failureSection).toContain("**review**");
  });

  // The failure section is the human's whole brief: it must name the preserved
  // branch and the exact `git worktree add` that continues it (not EnterWorktree),
  // and point at /implement.
  test("the failure section carries the continue-the-branch instruction", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["spec"],
    });
    expect(plan.failureSection).toContain("/implement 42");
    expect(plan.failureSection).toContain(
      "git worktree add ../issue-42 sandcastle/issue-42"
    );
    expect(plan.failureSection).toContain("sandcastle/issue-42");
  });

  // The reviewer's per-axis reason is embedded so the human sees why without
  // opening the run log.
  test("a per-axis reason is embedded in the failure section", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["spec"],
      reasons: { spec: "missing the idempotency requirement" },
    });
    expect(plan.failureSection).toContain(
      "missing the idempotency requirement"
    );
  });

  test("nothing → touches no label, preserves no branch, records nothing", () => {
    const plan = planOutcomeTransition({ kind: "nothing", issue: full });
    expect(plan.addLabel).toBeNull();
    expect(plan.removeLabels).toEqual([]);
    expect(plan.preserveBranch).toBe(false);
    expect(plan.completed).toBeUndefined();
  });

  // The completed record is what the run summary counts a build from.
  describe("the completed record a done outcome carries", () => {
    test("a full-mode issue keeps its forest position and topic group", () => {
      const plan = planOutcomeTransition({ kind: "done", issue: full });
      expect(plan.completed).toEqual({
        id: "42",
        title: "Add widget",
        branch: "sandcastle/issue-42",
        parents: ["7"],
        group: "widgets",
      });
    });

    test("an issue with no parents and an empty group carries neither", () => {
      const plan = planOutcomeTransition({
        kind: "done",
        issue: {
          id: "43",
          title: "Re-reviewed",
          branch: "sandcastle/issue-43",
          parents: [],
          group: "",
        },
      });
      expect(plan.completed).toEqual({
        id: "43",
        title: "Re-reviewed",
        branch: "sandcastle/issue-43",
        parents: [],
      });
      expect("group" in plan.completed).toBe(false);
    });

    test("an issue with an empty group key drops it too", () => {
      const plan = planOutcomeTransition({
        kind: "done",
        issue: { ...full, group: "" },
      });
      expect("group" in plan.completed).toBe(false);
    });
  });
});

describe("spliceReviewFailureSection", () => {
  const original = "# Fix the widget\n\nThe widget must foo the bar.";
  const section = "## Review failed\n\nspec: the bar was not fooed.";

  test("appends the delimited block when the body has none, keeping the original", () => {
    const out = spliceReviewFailureSection(original, section);
    expect(out).toContain("# Fix the widget");
    expect(out).toContain("The widget must foo the bar.");
    expect(out).toContain(REVIEW_FAILURE_BEGIN);
    expect(out).toContain(REVIEW_FAILURE_END);
    expect(out).toContain("the bar was not fooed.");
    expect(out.indexOf("foo the bar")).toBeLessThan(
      out.indexOf(REVIEW_FAILURE_BEGIN)
    );
  });

  test("replaces an existing block in place, not stacking a second one", () => {
    const once = spliceReviewFailureSection(original, section);
    const refreshed = spliceReviewFailureSection(
      once,
      "## Review failed\n\nstandards: naming is off."
    );
    const countOccurrences = (haystack, needle) =>
      haystack.split(needle).length - 1;
    expect(countOccurrences(refreshed, REVIEW_FAILURE_BEGIN)).toBe(1);
    expect(countOccurrences(refreshed, REVIEW_FAILURE_END)).toBe(1);
    expect(refreshed).toContain("naming is off.");
    expect(refreshed).not.toContain("the bar was not fooed.");
    expect(refreshed).toContain("The widget must foo the bar.");
  });

  test("splicing is idempotent for identical input (no drift, no duplication)", () => {
    const once = spliceReviewFailureSection(original, section);
    const twice = spliceReviewFailureSection(once, section);
    expect(twice).toBe(once);
  });

  test("an empty body yields just the block", () => {
    const out = spliceReviewFailureSection("", section);
    expect(out).toContain(REVIEW_FAILURE_BEGIN);
    expect(out).toContain(REVIEW_FAILURE_END);
    expect(out).toContain("the bar was not fooed.");
    expect(out.indexOf(REVIEW_FAILURE_BEGIN)).toBe(0);
  });

  test("text after an existing block is preserved when the block is replaced", () => {
    const withTrailer =
      original +
      "\n\n" +
      REVIEW_FAILURE_BEGIN +
      "\nold\n" +
      REVIEW_FAILURE_END +
      "\n\n## Appendix\n\nkeep me";
    const out = spliceReviewFailureSection(withTrailer, section);
    expect(out).toContain("## Appendix");
    expect(out).toContain("keep me");
    expect(out).not.toContain("old");
  });
});

// planFailureBodyEdit is the data-loss defence around the failure-section
// splice: a transient `gh` fetch error returns a null body, and that must
// never be turned into a ticket that holds ONLY the failure section.
describe("planFailureBodyEdit", () => {
  const section = "## Review failed\n\nspec: the bar was not fooed.";

  test("null body → skip, no edit produced", () => {
    const plan = planFailureBodyEdit(null, section);
    expect(plan).toEqual({ kind: "skip" });
  });

  test("present body → edit whose spliced body preserves the original and appends the section", () => {
    const original = "# Fix the widget\n\nThe widget must foo the bar.";
    const plan = planFailureBodyEdit(original, section);
    expect(plan.kind).toBe("edit");
    expect(plan.body).toContain("# Fix the widget");
    expect(plan.body).toContain("The widget must foo the bar.");
    expect(plan.body).toContain(REVIEW_FAILURE_BEGIN);
    expect(plan.body).toContain("the bar was not fooed.");
  });

  test("present body matches spliceReviewFailureSection's own output exactly", () => {
    const original = "# Fix the widget\n\nThe widget must foo the bar.";
    const plan = planFailureBodyEdit(original, section);
    expect(plan.body).toBe(spliceReviewFailureSection(original, section));
  });

  test("empty-string body is present, not null — still edits", () => {
    const plan = planFailureBodyEdit("", section);
    expect(plan.kind).toBe("edit");
    expect(plan.body).toContain(REVIEW_FAILURE_BEGIN);
  });
});
