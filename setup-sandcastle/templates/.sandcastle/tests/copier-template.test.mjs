import { test, expect, describe, beforeAll, afterAll } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// The template's install seam is `copier copy`. copier.yml lives at the REPO
// ROOT (with `_subdirectory: setup-sandcastle/templates/.sandcastle`), not in
// the template folder — that placement is load-bearing: copier only records
// `_commit` in the answers file when its source is the git root, and without
// `_commit` the breadcrumb pins no version and `copier update` has no ref to
// diff from. So we assert both the rendered tree AND that the breadcrumb
// records a `_commit` (issue #73). We observe the generated files, not copier
// internals.

const here = dirname(fileURLToPath(import.meta.url));
// tests/ -> .sandcastle/ -> templates/ -> setup-sandcastle/ -> repo root
const repoRoot = join(here, "..", "..", "..", "..");

function hasCopier() {
  try {
    execFileSync("copier", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

// copier is a documented install-time prereq (`uv tool install copier`); on a
// machine without it, skip rather than fail a red the env can't turn green.
describe.skipIf(!hasCopier())("copier copy renders the .sandcastle template", () => {
  let out;
  beforeAll(() => {
    out = mkdtempSync(join(tmpdir(), "sandcastle-copier-"));
    // Source is the repo root (a git root), no --vcs-ref: copier renders the
    // working tree AND records `_commit` from the source's HEAD, so the test
    // runs against uncommitted template edits and still proves version pinning.
    execFileSync(
      "copier",
      ["copy", "--defaults", "--data", "PYTHON_VERSION=3.14", repoRoot, join(out, ".sandcastle")],
      { encoding: "utf8" }
    );
  });
  afterAll(() => out && rmSync(out, { recursive: true, force: true }));

  const answers = () => readFileSync(join(out, ".sandcastle", ".copier-answers.yml"), "utf8");

  test("renders the orchestrator subtree, not the whole monorepo", () => {
    expect(existsSync(join(out, ".sandcastle", "main.mts"))).toBe(true);
    // If copier ignored `_subdirectory` it would dump the repo's skill folders
    // (setup-sandcastle/, code-review/, …) into .sandcastle/ instead.
    expect(existsSync(join(out, ".sandcastle", "setup-sandcastle"))).toBe(false);
  });

  test("excludes the dev-only tests/ suite", () => {
    expect(existsSync(join(out, ".sandcastle", "tests"))).toBe(false);
  });

  test("renders the PYTHON_VERSION answer into the Dockerfile", () => {
    const dockerfile = readFileSync(join(out, ".sandcastle", "Dockerfile"), "utf8");
    expect(dockerfile).toMatch(/^ARG PYTHON_VERSION=3\.14$/m);
  });

  test("breadcrumb pins the template version (records a non-empty _commit)", () => {
    expect(answers()).toMatch(/^_commit: .+$/m);
  });

  test("breadcrumb records the PYTHON_VERSION answer", () => {
    expect(answers()).toMatch(/PYTHON_VERSION: ['"]?3\.14['"]?/);
  });
});
