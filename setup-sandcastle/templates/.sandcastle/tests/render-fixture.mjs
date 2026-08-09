// Shared render fixture for the dev-only suite. Two test files now need a real
// copier render — copier-template.test.mjs to observe the install seam, and
// sandbox-identity.test.mjs to import a module that only exists once rendered —
// and both need the same answer to "is copier here at all". Keeping one copy
// matters beyond tidiness: issue #112 tracks these skips reading as a silent
// green, and whatever fixes it should be one edit, not one per test file.
//
// Not a `.test.mjs`, so vitest collects no suite from it; `tests/` is excluded
// from the render, so none of this ships to an adopter.
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// copier is a documented install-time prereq (`uv tool install copier`); on a
// machine without it, skip rather than fail a red the env can't turn green.
export function hasCopier() {
  return spawnSync("copier", ["--version"], { stdio: "ignore" }).status === 0;
}

/**
 * Render the live template's Python arm into a fresh temp directory and return
 * its path. `PYTHON_VERSION` is pinned to a value no adopter uses so an
 * assertion cannot pass on a coincidence with the copier.yml default.
 *
 * `linkModules` symlinks the dev home's `node_modules` into the render: the
 * render lands outside the dev home, where neither `@ai-hero/sandcastle` nor
 * `@types/node` would resolve. Needed by anything that imports or typechecks
 * the rendered orchestrator.
 */
export function renderPythonArm(repoRoot, { linkModules = false } = {}) {
  const target = mkdtempSync(join(tmpdir(), "sandcastle-render-"));
  execFileSync(
    "copier",
    ["copy", "--defaults", "--data", "PYTHON_VERSION=3.14", repoRoot, target],
    { encoding: "utf8" }
  );
  if (linkModules) {
    symlinkSync(join(repoRoot, "setup-sandcastle", "node_modules"), join(target, "node_modules"));
  }
  return target;
}
