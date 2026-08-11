import { test, expect, describe } from "vitest";
import {
  spliceReviewFailureSection,
  REVIEW_FAILURE_BEGIN,
  REVIEW_FAILURE_END,
} from "../issue-body.mts";

const countOccurrences = (haystack, needle) =>
  haystack.split(needle).length - 1;

describe("spliceReviewFailureSection", () => {
  const original = "# Fix the widget\n\nThe widget must foo the bar.";
  const section = "## Review failed\n\nspec: the bar was not fooed.";

  test("appends the delimited block when the body has none, keeping the original", () => {
    const out = spliceReviewFailureSection(original, section);
    // Original text survives verbatim.
    expect(out).toContain("# Fix the widget");
    expect(out).toContain("The widget must foo the bar.");
    // The section is present, wrapped in the markers.
    expect(out).toContain(REVIEW_FAILURE_BEGIN);
    expect(out).toContain(REVIEW_FAILURE_END);
    expect(out).toContain("the bar was not fooed.");
    // Original comes before the appended block.
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
    // Exactly one delimited block after a re-run.
    expect(countOccurrences(refreshed, REVIEW_FAILURE_BEGIN)).toBe(1);
    expect(countOccurrences(refreshed, REVIEW_FAILURE_END)).toBe(1);
    // New content in, stale content gone.
    expect(refreshed).toContain("naming is off.");
    expect(refreshed).not.toContain("the bar was not fooed.");
    // Original ticket text still intact.
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
    expect(countOccurrences(out, REVIEW_FAILURE_BEGIN)).toBe(1);
  });
});
