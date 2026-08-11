import { test, expect, describe, beforeAll, afterAll } from "vitest";
import { execFileSync } from "node:child_process";
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const promptPath = join(repoRoot, ".sandcastle", "review-standards-prompt.md");

// The standards judge loads each CODING_STANDARDS.md conditionally,
// keyed on what the branch diff touches. The conditional logic
// lives in `!`bash`` snippets of the form
//   git diff --name-only ... | grep -qE '<pattern>' && cat <file>
// We test the OBSERVABLE behavior of those snippets: given a set of changed
// paths, which standards file (if any) gets emitted.
//
// We extract the grep+cat commands straight from the prompt (single source of
// truth) and feed them a synthetic diff path-set via a fake `git` on PATH, so
// the test breaks if the prompt's selection logic regresses.

// The snippets `cat` two relative paths — `CODING_STANDARDS.md` and
// `.sandcastle/CODING_STANDARDS.md` — that only exist in a real target repo.
// We synthesize both in a temp dir with known first-line markers and run the
// snippets there, so the test owns its fixtures instead of depending on stray
// standards files living in the template tree.
const ROOT_MARKER = "# Project coding standards (test fixture)";
const SANDCASTLE_MARKER = "# Sandcastle coding standards (test fixture)";

let fixtureDir;
beforeAll(() => {
  fixtureDir = mkdtempSync(join(tmpdir(), "review-standards-"));
  writeFileSync(join(fixtureDir, "CODING_STANDARDS.md"), `${ROOT_MARKER}\n`);
  mkdirSync(join(fixtureDir, ".sandcastle"));
  writeFileSync(
    join(fixtureDir, ".sandcastle", "CODING_STANDARDS.md"),
    `${SANDCASTLE_MARKER}\n`
  );
});
afterAll(() => rmSync(fixtureDir, { recursive: true, force: true }));

/** Pull the `!`...`` ` bash snippets that pipe a diff into grep && cat. */
function extractStandardsSnippets() {
  const prompt = readFileSync(promptPath, "utf8");
  const snippets = [];
  // `!`<cmd>`` — Sandcastle's bash-expansion syntax.
  const re = /!`([^`]*grep[^`]*cat[^`]*)`/g;
  let m;
  while ((m = re.exec(prompt)) !== null) snippets.push(m[1]);
  return snippets;
}

/**
 * Run every standards snippet with `git diff --name-only` stubbed to print
 * `paths`. Returns the concatenated stdout (i.e. whichever standards files the
 * snippets chose to cat). Runs from the temp fixture dir so the snippets'
 * relative cat paths resolve to our synthesized markers.
 */
function runSnippets(paths) {
  const snippets = extractStandardsSnippets();
  // Shadow `git` with a shell function that ignores its args and prints the
  // synthetic path-set, so the snippet's real `git diff` is replaced.
  const stub = `git() { printf '%s\\n' ${paths.map((p) => `'${p}'`).join(" ")}; }\n`;
  let out = "";
  for (const snippet of snippets) {
    const script = stub + snippet;
    // `grep -q` exits non-zero on no match, so the pipeline exits non-zero and
    // `&& cat` yields nothing — the documented clean "load neither" path. Treat
    // a non-zero exit as empty output, not a test failure.
    try {
      out += execFileSync("bash", ["-c", script], {
        cwd: fixtureDir,
        encoding: "utf8",
      });
    } catch (e) {
      out += e.stdout ?? "";
    }
  }
  return out;
}

describe("review-standards-prompt: diff-aware CODING_STANDARDS loading", () => {
  test("a diff under src/ loads the project standards only", () => {
    const out = runSnippets(["src/rag_bootcamp/pipeline.py"]);
    expect(out).toContain(ROOT_MARKER);
    expect(out).not.toContain(SANDCASTLE_MARKER);
  });

  test("an interleaved test under src/ (…_test.py) loads the project standards", () => {
    const out = runSnippets(["src/rag_bootcamp/pipeline_test.py"]);
    expect(out).toContain(ROOT_MARKER);
    expect(out).not.toContain(SANDCASTLE_MARKER);
  });

  test("a diff under .sandcastle/ loads the Sandcastle standards only", () => {
    const out = runSnippets([".sandcastle/main.mts"]);
    expect(out).toContain(SANDCASTLE_MARKER);
    expect(out).not.toContain(ROOT_MARKER);
  });

  test("a docs-only diff loads neither", () => {
    const out = runSnippets(["docs/adr/0008.md", "README.md"]);
    expect(out).not.toContain(ROOT_MARKER);
    expect(out).not.toContain(SANDCASTLE_MARKER);
  });

  // Sandcastle tests live under `.sandcastle/tests/` — they must map to the
  // Sandcastle standards, NOT the project ones. `^src/` must not catch
  // `.sandcastle/`, and `^\.sandcastle/` must catch its tests.
  test("a diff under .sandcastle/tests/ loads the Sandcastle standards only", () => {
    const out = runSnippets([".sandcastle/tests/reconcile.test.mjs"]);
    expect(out).toContain(SANDCASTLE_MARKER);
    expect(out).not.toContain(ROOT_MARKER);
  });
});
