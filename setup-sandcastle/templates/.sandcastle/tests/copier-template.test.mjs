import { test, expect, describe, beforeAll, afterAll } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// The template's install seam is `copier copy`: pointed at this template
// (copier.yml + the `.sandcastle` subdirectory), it must produce a target's
// runtime `.sandcastle/` — the dev-only `tests/` left out, `PYTHON_VERSION`
// rendered into the Dockerfile from an answer, and the answers-file breadcrumb
// written so the repo records which template version it sits on. We observe the
// generated file tree, not copier internals (issue #73).

const here = dirname(fileURLToPath(import.meta.url));
// tests/ -> .sandcastle/ -> templates/  (templates/ holds copier.yml)
const templateRoot = join(here, "..", "..");

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
    // Local path, no --vcs-ref: copier renders the working tree, so the test
    // runs against uncommitted template edits.
    execFileSync(
      "copier",
      ["copy", "--defaults", "--data", "PYTHON_VERSION=3.14", templateRoot, out],
      { encoding: "utf8" }
    );
  });
  afterAll(() => out && rmSync(out, { recursive: true, force: true }));

  test("excludes the dev-only tests/ suite", () => {
    expect(existsSync(join(out, "tests"))).toBe(false);
  });

  test("renders the PYTHON_VERSION answer into the Dockerfile", () => {
    const dockerfile = readFileSync(join(out, "Dockerfile"), "utf8");
    expect(dockerfile).toMatch(/^ARG PYTHON_VERSION=3\.14$/m);
  });

  test("writes the .copier-answers.yml breadcrumb pinning the answer", () => {
    const answers = readFileSync(join(out, ".copier-answers.yml"), "utf8");
    expect(answers).toMatch(/PYTHON_VERSION: ['"]?3\.14['"]?/);
  });
});
