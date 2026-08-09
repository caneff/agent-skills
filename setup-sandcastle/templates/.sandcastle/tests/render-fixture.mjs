// Shared fixtures for the dev-only suite: a real copier render, and a repo the
// install script's preflight can be run against. Two test files need the
// render — copier-template.test.mjs to observe the install seam, and
// sandbox-identity.test.mjs to import a module that only exists once rendered —
// and both need the same answer to "is copier here at all". Keeping one copy
// matters beyond tidiness: issue #112 tracks these skips reading as a silent
// green, and whatever fixes it should be one edit, not one per test file.
//
// Not a `.test.mjs`, so vitest collects no suite from it; `tests/` is excluded
// from the render, so none of this ships to an adopter.
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
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

const shim = (bin, name, body) => {
  writeFileSync(join(bin, name), `#!/bin/sh\n${body}\n`, { mode: 0o755 });
};

/**
 * A repo that passes every preflight check for `arm`, with nothing real
 * installed: `PATH` is shimmed with fake `docker`, `copier`, `node`, `npx` and
 * `just`, and `HOME` points at a fixture home carrying the `tdd` skill. The
 * shimmed `PATH` keeps only `/usr/bin` and `/bin`, so a prereq the fixture does
 * not shim is genuinely absent — the machine's real Docker or copier cannot
 * turn an omitted row green.
 *
 * Tests break one prereq at a time, then `run()` the script against it.
 *
 * `realTools` is for the one end-to-end run: it keeps the real `PATH` behind
 * the shim dir so `copier`, `npm` and `npx` are the machine's own, shims only
 * `docker` (whose daemon the install never actually needs) and `just`, and
 * hands over the real `HOME` — the render clones a private template over
 * https, so it needs the machine's git credentials, and the `tdd` skill the
 * fixture home fakes is a real prereq of the machine running this test.
 */
export function preflightFixture(repoRoot, arm, { realTools = false } = {}) {
  const root = mkdtempSync(join(tmpdir(), "sandcastle-preflight-"));
  const home = join(root, "home");
  const bin = join(root, "bin");
  const repo = join(root, "repo");
  mkdirSync(join(home, ".claude", "skills", "tdd"), { recursive: true });
  writeFileSync(join(home, ".claude", "skills", "tdd", "SKILL.md"), "# tdd\n");
  mkdirSync(bin, { recursive: true });
  shim(bin, "docker", "exit 0");
  shim(bin, "just", 'printf "Available recipes:\\n    check\\n    lint\\n    typecheck\\n"');
  if (!realTools) {
    shim(bin, "copier", "exit 0");
    // Real node: preflight reads package.json's `scripts` block with it. Rows
    // that need node absent delete this shim rather than stubbing it out.
    shim(bin, "node", `exec ${process.execPath} "$@"`);
    shim(bin, "npx", "exit 0");
  }

  mkdirSync(join(repo, ".github", "workflows"), { recursive: true });
  writeFileSync(join(repo, ".github", "workflows", "ci.yml"), "on: pull_request\n");
  writeFileSync(join(repo, "CODING_STANDARDS.md"), "# standards\n");
  writeFileSync(join(repo, "AGENTS.md"), "# agents\n");
  if (arm === "python") {
    writeFileSync(join(repo, ".python-version"), "3.14\n");
  } else {
    writeFileSync(
      join(repo, "package.json"),
      JSON.stringify({ scripts: { lint: "x", typecheck: "x", test: "x" } }, null, 2) + "\n"
    );
  }
  execFileSync("git", ["-C", repo, "init", "-q", "-b", "main"]);

  return {
    root,
    home,
    bin,
    repo,
    shim: (name, body) => shim(bin, name, body),
    run(args = [arm, "--preflight"]) {
      return spawnSync(join(repoRoot, "setup-sandcastle", "install"), args, {
        cwd: repo,
        encoding: "utf8",
        env: realTools
          ? { HOME: process.env.HOME, PATH: `${bin}:${process.env.PATH}` }
          : { HOME: home, PATH: `${bin}:/usr/bin:/bin` },
      });
    },
  };
}
