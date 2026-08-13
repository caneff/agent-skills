// The review-failure body splice moved to issue-lifecycle.mts — the issue-
// lifecycle vocabulary's one home (#274). Re-exported here so this path keeps
// resolving for anything still importing it; new code should import directly
// from ./issue-lifecycle.mts.
export {
  spliceReviewFailureSection,
  REVIEW_FAILURE_BEGIN,
  REVIEW_FAILURE_END,
} from "./issue-lifecycle.mts";
