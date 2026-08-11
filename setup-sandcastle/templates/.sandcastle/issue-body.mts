// Splice Sandcastle's one review-failure section into an issue body without
// disturbing the rest of the ticket.
//
// When a two-axis review fails, the orchestrator writes the failure context
// (which axis, why, how to continue the preserved branch) INTO the issue body
// so a human re-driving it with `/implement` reads the instruction as part of
// its brief (#240 story 15a). That write is a read-modify-write: the section is
// fenced by two HTML-comment markers — invisible in rendered markdown, exact to
// match — so a re-run REPLACES the block in place rather than stacking a second
// copy, and the original spec text is never touched.

export const REVIEW_FAILURE_BEGIN = "<!-- sandcastle:review-failure -->";
export const REVIEW_FAILURE_END = "<!-- /sandcastle:review-failure -->";

// Return `body` with `section` fenced between the markers: replacing an existing
// fenced block if one is present, appending it (separated by a blank line) if
// not. Pure string→string; the caller does the `gh issue edit`.
export function spliceReviewFailureSection(
  body: string,
  section: string
): string {
  const block = `${REVIEW_FAILURE_BEGIN}\n${section}\n${REVIEW_FAILURE_END}`;

  const start = body.indexOf(REVIEW_FAILURE_BEGIN);
  const end = body.indexOf(REVIEW_FAILURE_END);
  if (start !== -1 && end !== -1 && end > start) {
    // Replace in place; keep everything before the opening marker and after the
    // closing one (a human may have written notes below our block).
    return body.slice(0, start) + block + body.slice(end + REVIEW_FAILURE_END.length);
  }

  const trimmed = body.replace(/\s+$/, "");
  return trimmed.length ? `${trimmed}\n\n${block}\n` : `${block}\n`;
}
