import { test, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// Stage 2 of #340 (issue #343): pr-prompt.md must open each PR against the
// per-issue resolved base (a stacked child's parent branch, or `main` for a
// root issue) rather than a hardcoded `main`. `{{BASE}}` is a runtime
// promptArgs placeholder — see the "template delimiters do not collide with
// runtime placeholders" describe block in copier-template.test.mjs for why
// `{{ }}` survives a copier render untouched.
const here = dirname(fileURLToPath(import.meta.url));
const prPrompt = readFileSync(join(here, "..", "pr-prompt.md"), "utf8");

test("pr-prompt.md opens the PR against the resolved base, not a hardcoded main", () => {
  expect(prPrompt).toContain("--base {{BASE}}");
  expect(prPrompt).not.toContain("--base main");
});
