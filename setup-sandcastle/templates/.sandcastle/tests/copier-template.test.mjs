import { test, expect, describe, beforeAll, afterAll } from "vitest";
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync, appendFileSync, writeFileSync, cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// The template's install seam is `copier copy`/`copier update`. copier.yml
// lives at the REPO ROOT (with `_subdirectory: setup-sandcastle/templates`),
// not in the template folder — that placement is load-bearing: copier only
// records `_commit` in the answers file when its source is the git root, and
// without `_commit` the breadcrumb pins no version and `copier update` has no
// ref to diff from. The subproject root the template installs into is the
// TARGET's git root, with `.sandcastle/` rendered as a subtree beneath it
// (issue #93) — that layout is what lets `copier update` resolve its diff and
// do a real 3-way merge. We observe the generated files and update's exit
// status, not copier internals.

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
describe.skipIf(!hasCopier())("copier copy renders the orchestrator at the git root", () => {
  let target;
  beforeAll(() => {
    // The subproject root is the target's git root; render straight into it and
    // `.sandcastle/` lands as a subtree. Source is the repo root (a git root),
    // no --vcs-ref: copier renders the working tree AND records `_commit` from
    // the source's HEAD, so the test runs against uncommitted template edits and
    // still proves version pinning.
    target = mkdtempSync(join(tmpdir(), "sandcastle-copier-"));
    execFileSync(
      "copier",
      ["copy", "--defaults", "--data", "PYTHON_VERSION=3.14", repoRoot, target],
      { encoding: "utf8" }
    );
  });
  afterAll(() => target && rmSync(target, { recursive: true, force: true }));

  const answers = () => readFileSync(join(target, ".copier-answers.yml"), "utf8");

  test("renders the orchestrator subtree, not the whole monorepo", () => {
    expect(existsSync(join(target, ".sandcastle", "main.mts"))).toBe(true);
    // If copier ignored `_subdirectory` it would dump the repo's skill folders
    // (setup-sandcastle/, code-review/, …) into the target instead.
    expect(existsSync(join(target, "setup-sandcastle"))).toBe(false);
  });

  test("scatters nothing across the target root except .sandcastle and the breadcrumb", () => {
    // Only .sandcastle/ (and its breadcrumb) should land — no dev-home files
    // (package.json, vitest.config.mjs) leaking into the adopter's root.
    expect(existsSync(join(target, "package.json"))).toBe(false);
    expect(existsSync(join(target, "vitest.config.mjs"))).toBe(false);
  });

  test("excludes the dev-only tests/ suite", () => {
    expect(existsSync(join(target, ".sandcastle", "tests"))).toBe(false);
  });

  test("renders the PYTHON_VERSION answer into the Dockerfile", () => {
    const dockerfile = readFileSync(join(target, ".sandcastle", "Dockerfile"), "utf8");
    expect(dockerfile).toMatch(/^ARG PYTHON_VERSION=3\.14$/m);
  });

  test("breadcrumb lands at the repo root and pins a non-empty _commit", () => {
    expect(existsSync(join(target, ".copier-answers.yml"))).toBe(true);
    expect(answers()).toMatch(/^_commit: .+$/m);
  });

  test("breadcrumb records the PYTHON_VERSION answer", () => {
    expect(answers()).toMatch(/PYTHON_VERSION: ['"]?3\.14['"]?/);
  });
});

// The template fills its own blanks with `[[ ]]` / `[% %]` (copier `_envops`),
// because the prompt-drawer files carry their OWN `{{TASK_ID}}` / `{{BRANCH}}`
// placeholders that the agent expands at run time. Under copier's default
// delimiters the two styles are the same syntax, so the moment a prompt file
// becomes renderable copier eats the runtime placeholders.
//
// The live template has no renderable file carrying both styles yet, so the
// probe supplies one: a throwaway `.jinja` file dropped into a fixture copy of
// the live `copier.yml` + templates. It renders through the real config, so it
// fails if `_envops` is missing or wrong.
describe.skipIf(!hasCopier())("template delimiters do not collide with runtime placeholders", () => {
  let src;
  let target;
  const PROBE = ".sandcastle/envops-probe.txt";

  beforeAll(() => {
    src = mkdtempSync(join(tmpdir(), "sandcastle-envops-src-"));
    cpSync(join(repoRoot, "copier.yml"), join(src, "copier.yml"));
    cpSync(
      join(repoRoot, "setup-sandcastle", "templates"),
      join(src, "setup-sandcastle", "templates"),
      { recursive: true }
    );
    writeFileSync(
      join(src, "setup-sandcastle", "templates", `${PROBE}.jinja`),
      "runtime: {{TASK_ID}}\nanswer: [[ PYTHON_VERSION ]]\nblock: [% if PYTHON_VERSION %]yes[% endif %]\n"
    );
    target = mkdtempSync(join(tmpdir(), "sandcastle-envops-tgt-"));
    execFileSync(
      "copier",
      ["copy", "--defaults", "--data", "PYTHON_VERSION=3.14", src, target],
      { encoding: "utf8" }
    );
  });
  afterAll(() => {
    if (src) rmSync(src, { recursive: true, force: true });
    if (target) rmSync(target, { recursive: true, force: true });
  });

  test("leaves a runtime {{ }} placeholder untouched in a rendered file", () => {
    expect(readFileSync(join(target, PROBE), "utf8")).toMatch(/^runtime: \{\{TASK_ID\}\}$/m);
  });

  test("expands an answer written with the template's own delimiters", () => {
    const rendered = readFileSync(join(target, PROBE), "utf8");
    expect(rendered).toMatch(/^answer: 3\.14$/m);
    expect(rendered).toMatch(/^block: yes$/m);
  });
});

// The regression that proves the capability: a copy→update round-trip run from
// the target's git root completes and does a REAL 3-way merge. On the old subdir
// layout the breadcrumb sat at `.sandcastle/.copier-answers.yml`, so `copier
// update` at the root could not find it and died ("Template not found"); with the
// subproject root at the git root, update resolves and merges.
//
// It needs two committed, tagged template versions to diff — copier re-clones the
// source by the recorded `_commit`, which a dirty local worktree can't satisfy.
// So we build a self-contained fixture: a throwaway git repo holding the LIVE
// `copier.yml` + `templates/`, tagged v1→v2, exercising the real layout hermetically.
describe.skipIf(!hasCopier())("copier update round-trips from the git root", () => {
  let src;
  let target;
  let update;
  const ADOPTER = "<!-- adopter-local-edit -->";
  const TEMPLATE_V2 = "<!-- template-v2-change -->";
  const V1 = "sandcastle-template/vtest1";
  const V2 = "sandcastle-template/vtest2";
  const contextInSrc = () => join(src, "setup-sandcastle", "templates", ".sandcastle", "CONTEXT.md");
  const contextInTarget = () => join(target, ".sandcastle", "CONTEXT.md");
  const gitIn = (dir) => (...args) => execFileSync("git", ["-C", dir, ...args], { encoding: "utf8" });
  const initRepo = (dir) => {
    const g = gitIn(dir);
    g("init", "-q");
    g("config", "user.email", "test@example.com");
    g("config", "user.name", "Test");
    return g;
  };

  beforeAll(() => {
    // --- fixture: a self-contained template repo built from the live files ---
    src = mkdtempSync(join(tmpdir(), "sandcastle-src-"));
    cpSync(join(repoRoot, "copier.yml"), join(src, "copier.yml"));
    cpSync(
      join(repoRoot, "setup-sandcastle", "templates"),
      join(src, "setup-sandcastle", "templates"),
      { recursive: true }
    );
    const gsrc = initRepo(src);
    gsrc("add", "-A");
    gsrc("commit", "-q", "-m", "v1");
    gsrc("tag", V1);

    // --- adopter installs v1 into its git root, then commits ---
    target = mkdtempSync(join(tmpdir(), "sandcastle-tgt-"));
    const gtgt = initRepo(target);
    writeFileSync(join(target, ".python-version"), "3.14\n");
    gtgt("add", "-A");
    gtgt("commit", "-q", "-m", "init target");
    execFileSync(
      "copier",
      ["copy", "--defaults", "--vcs-ref", V1, "--data", "PYTHON_VERSION=3.14", src, target],
      { encoding: "utf8" }
    );
    gtgt("add", "-A");
    gtgt("commit", "-q", "-m", "install sandcastle");

    // A legitimate adopter edit to a template-owned file — the thing a re-render
    // hack would silently clobber but a real 3-way merge must preserve.
    appendFileSync(contextInTarget(), `\n${ADOPTER}\n`);
    gtgt("add", "-A");
    gtgt("commit", "-q", "-m", "adopter edit");

    // --- template evolves to v2 ---
    appendFileSync(contextInSrc(), `\n${TEMPLATE_V2}\n`);
    gsrc("commit", "-q", "-am", "v2");
    gsrc("tag", V2);

    // Update v1 -> v2 from the git root — no cd into .sandcastle.
    update = spawnSync("copier", ["update", "--defaults", "--trust", "--vcs-ref", V2], {
      cwd: target,
      encoding: "utf8",
    });
  });
  afterAll(() => {
    if (src) rmSync(src, { recursive: true, force: true });
    if (target) rmSync(target, { recursive: true, force: true });
  });

  test("copier update completes (exit 0) run from the git root", () => {
    expect(update.status, update.stderr).toBe(0);
  });

  test("keeps the breadcrumb at the root and the subtree under .sandcastle", () => {
    expect(existsSync(join(target, ".copier-answers.yml"))).toBe(true);
    expect(existsSync(join(target, ".sandcastle", "main.mts"))).toBe(true);
  });

  test("3-way merge preserves the adopter's local edit", () => {
    expect(readFileSync(contextInTarget(), "utf8")).toContain(ADOPTER);
  });

  test("3-way merge lands the new template version's change", () => {
    expect(readFileSync(contextInTarget(), "utf8")).toContain(TEMPLATE_V2);
  });
});
