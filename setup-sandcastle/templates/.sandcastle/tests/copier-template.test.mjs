import { test, expect, describe, beforeAll, afterAll } from "vitest";
import { execFileSync, spawnSync } from "node:child_process";
import {
  existsSync,
  readFileSync,
  readdirSync,
  appendFileSync,
  writeFileSync,
  cpSync,
  mkdtempSync,
  rmSync,
} from "node:fs";
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
const BREADCRUMB = ".copier-answers.yml";

// Several blocks below need a throwaway template repo holding the LIVE files,
// because copier re-clones its source by the recorded `_commit` and a dirty
// local worktree can't satisfy that. Same two files every time: the root
// `copier.yml` and the `templates/` subdirectory it reaches into.
function copyLiveTemplateInto(src) {
  cpSync(join(repoRoot, "copier.yml"), join(src, "copier.yml"));
  cpSync(
    join(repoRoot, "setup-sandcastle", "templates"),
    join(src, "setup-sandcastle", "templates"),
    { recursive: true }
  );
}

const discard = (...dirs) =>
  dirs.forEach((d) => d && rmSync(d, { recursive: true, force: true }));

const gitIn = (dir) => (...args) => execFileSync("git", ["-C", dir, ...args], { encoding: "utf8" });

const initRepo = (dir) => {
  const g = gitIn(dir);
  g("init", "-q");
  g("config", "user.email", "test@example.com");
  g("config", "user.name", "Test");
  return g;
};

// Every fixture reads the same file to ask what an adopter answered.
const answersIn = (dir) => readFileSync(join(dir, BREADCRUMB), "utf8");

// Answers are matched line-anchored. A bare substring would also match a value
// commented out, indented under another key, or prefixing a longer line.
const recordedAnswer = (name, value) =>
  new RegExp(`^${name}: ['"]?${value.replace(".", "\\.")}['"]?$`, "m");

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

  // Nobody answered LANGUAGE here, and the render still records one. Why that
  // default is load-bearing rather than a courtesy: see `copier.yml`.
  test("breadcrumb records LANGUAGE, defaulted to python when unanswered", () => {
    expect(answers()).toMatch(recordedAnswer("LANGUAGE", "python"));
  });
});

// Why the template renders with `[[ ]]` / `[% %]` instead of copier's defaults:
// see the `_envops` comment in `copier.yml`. What matters here is the behaviour
// it buys — a run-time `{{ }}` placeholder passes through a render untouched.
//
// The live template has no renderable file carrying both styles yet (the prompt
// drawer is plain `.md`, so copier copies it verbatim), so the probe supplies
// one: a throwaway `.jinja` dropped into a fixture copy of the live template. It
// renders through the real `copier.yml`, so it fails if `_envops` is missing or
// wrong.
describe.skipIf(!hasCopier())("template delimiters do not collide with runtime placeholders", () => {
  let src;
  let target;
  const PROBE = ".sandcastle/envops-probe.txt";
  const rendered = () => readFileSync(join(target, PROBE), "utf8");

  beforeAll(() => {
    src = mkdtempSync(join(tmpdir(), "sandcastle-envops-src-"));
    copyLiveTemplateInto(src);
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
  afterAll(() => discard(src, target));

  test("leaves a runtime {{ }} placeholder untouched in a rendered file", () => {
    expect(rendered()).toMatch(/^runtime: \{\{TASK_ID\}\}$/m);
  });

  test("expands a variable written with the template's own delimiters", () => {
    expect(rendered()).toMatch(/^answer: 3\.14$/m);
  });

  test("expands a block written with the template's own delimiters", () => {
    expect(rendered()).toMatch(/^block: yes$/m);
  });
});

// The adopters' regression net. Three live repos run this template, and the
// promise across the whole LANGUAGE arc (issue #131) is that a Python adopter's
// render never moves — not for the delimiter switch here, and not for the
// branching the later tickets add. So we render the template as it stood BEFORE
// the arc began and diff it against today's render, file by file.
//
// The promise covers the rendered FILES. The breadcrumb is copier's own
// bookkeeping and is expected to grow: `_commit` records where a render came
// from, and each ticket in the arc adds the answers it introduces. So its path
// is compared (a rename there broke the install once) but its contents are
// asserted on their own, below, rather than pinned byte-for-byte.
//
// Re-pin PRE_ARC only when a render is deliberately changed for the Python arm,
// and say so in the commit — that is the whole point of the assertion.
const PRE_ARC = "59c7941"; // last commit before the LANGUAGE arc (issue #131)

// Answers each arc ticket deliberately ADDS to a Python adopter's breadcrumb.
// The net below demands the breadcrumb equal the pre-arc one plus exactly these,
// so a ticket declares its addition instead of the assertion quietly widening.
const ARC_ADDED_ANSWERS = ["LANGUAGE: python"];

function renderedTree(root) {
  const files = new Map();
  for (const entry of readdirSync(root, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile()) continue;
    const rel = join(entry.parentPath, entry.name).slice(root.length + 1);
    if (rel.startsWith(".git/")) continue;
    files.set(rel, readFileSync(join(root, rel), "utf8"));
  }
  return files;
}

describe.skipIf(!hasCopier())("the delimiter switch is invisible to an adopter", () => {
  let src;
  let before;
  let after;
  let adopter;
  let update;
  const PRE = "sandcastle-template/vpre";
  const POST = "sandcastle-template/vpost";
  const render = (ref) => {
    const target = mkdtempSync(join(tmpdir(), "sandcastle-arc-tgt-"));
    execFileSync(
      "copier",
      ["copy", "--defaults", "--vcs-ref", ref, "--data", "PYTHON_VERSION=3.14", src, target],
      { encoding: "utf8" }
    );
    return target;
  };

  beforeAll(() => {
    // One fixture template repo carrying both versions: `git archive` gives the
    // pre-arc tree without disturbing this worktree, then the live files
    // overwrite it as a second commit.
    src = mkdtempSync(join(tmpdir(), "sandcastle-arc-src-"));
    const tar = join(src, "pre.tar");
    execFileSync("git", ["-C", repoRoot, "archive", "--format=tar", "-o", tar, PRE_ARC]);
    execFileSync("tar", ["-xf", tar, "-C", src]);
    rmSync(tar);
    const gsrc = initRepo(src);
    gsrc("add", "-A");
    gsrc("commit", "-q", "-m", "pre-arc");
    gsrc("tag", PRE);

    before = render(PRE);

    // An adopter that installed the pre-arc template, before the template moves on.
    adopter = mkdtempSync(join(tmpdir(), "sandcastle-arc-adopter-"));
    const gadopt = initRepo(adopter);
    writeFileSync(join(adopter, ".python-version"), "3.14\n");
    gadopt("add", "-A");
    gadopt("commit", "-q", "-m", "init adopter");
    execFileSync(
      "copier",
      ["copy", "--defaults", "--vcs-ref", PRE, "--data", "PYTHON_VERSION=3.14", src, adopter],
      { encoding: "utf8" }
    );
    gadopt("add", "-A");
    gadopt("commit", "-q", "-m", "install sandcastle");

    // The template moves to today's files. `templates/` goes first: the answers
    // file was RENAMED, so a plain overwrite would leave both names behind.
    rmSync(join(src, "setup-sandcastle", "templates"), { recursive: true, force: true });
    copyLiveTemplateInto(src);
    gsrc("add", "-A");
    gsrc("commit", "-q", "-m", "post-arc");
    gsrc("tag", POST);

    after = render(POST);
    update = spawnSync("copier", ["update", "--defaults", "--trust", "--vcs-ref", POST], {
      cwd: adopter,
      encoding: "utf8",
    });
  });
  afterAll(() => discard(src, before, after, adopter));

  test("renders the same set of files as the pre-arc template", () => {
    expect([...renderedTree(after).keys()].sort()).toEqual([...renderedTree(before).keys()].sort());
  });

  test("renders every file byte-identically to the pre-arc template", () => {
    const [was, is] = [renderedTree(before), renderedTree(after)];
    for (const [path, body] of was) {
      if (path === BREADCRUMB) continue;
      expect(is.get(path), path).toBe(body);
    }
  });

  // Both directions. Subset-only would prove the pre-arc answers survived while
  // letting a stray or duplicated answer leak into three live adopters unseen.
  test("records the pre-arc answers plus exactly what the arc declares it added", () => {
    const recorded = (tree) =>
      tree
        .get(BREADCRUMB)
        .split("\n")
        .filter((line) => line && !line.startsWith("_") && !line.startsWith("#"));
    expect(recorded(renderedTree(after)).sort()).toEqual(
      [...recorded(renderedTree(before)), ...ARC_ADDED_ANSWERS].sort()
    );
  });

  test("copier update from a pre-arc breadcrumb completes (exit 0)", () => {
    expect(update.status, update.stderr).toBe(0);
  });

  test("the updated adopter's breadcrumb keeps its answers and its path", () => {
    expect(existsSync(join(adopter, BREADCRUMB))).toBe(true);
    expect(answersIn(adopter)).toMatch(recordedAnswer("PYTHON_VERSION", "3.14"));
  });

  // An adopter whose breadcrumb predates the question takes the default on
  // update, silently. Without a default this update would have aborted rather
  // than reached here — see the mutation noted in `copier.yml`.
  test("an adopter installed before LANGUAGE existed takes the default on update", () => {
    expect(answersIn(adopter)).toMatch(recordedAnswer("LANGUAGE", "python"));
  });
});

// The Node arm. Nothing in the RENDER branches on LANGUAGE yet — that arrives
// with the later tickets — so what this proves is the answer travelling end to
// end: question, breadcrumb, and the update that follows.
//
// `PYTHON_VERSION` is conditional on the Python arm, and copier drops an unasked
// conditional answer from the breadcrumb. That is the point: a Node adopter's
// recorded Python version disappears on its own instead of lingering as noise
// for the propagate sweep to read back and re-assert.
describe.skipIf(!hasCopier())("a node adopter", () => {
  let src;
  let fresh;
  let corrected;
  let asInstalled;
  let correction;
  let sweep;
  const V1 = "sandcastle-template/vnode1";
  const V2 = "sandcastle-template/vnode2";
  const V3 = "sandcastle-template/vnode3";
  const bump = (gsrc, tag) => {
    appendFileSync(join(src, "setup-sandcastle", "templates", ".sandcastle", "CONTEXT.md"), "\n");
    gsrc("commit", "-q", "-am", tag);
    gsrc("tag", tag);
  };

  beforeAll(() => {
    src = mkdtempSync(join(tmpdir(), "sandcastle-node-src-"));
    copyLiveTemplateInto(src);
    const gsrc = initRepo(src);
    gsrc("add", "-A");
    gsrc("commit", "-q", "-m", "v1");
    gsrc("tag", V1);

    // A repo that says node at install time.
    fresh = mkdtempSync(join(tmpdir(), "sandcastle-node-fresh-"));
    execFileSync(
      "copier",
      ["copy", "--defaults", "--vcs-ref", V1, "--data", "LANGUAGE=node", src, fresh],
      { encoding: "utf8" }
    );

    // The real migration path: a repo that installed BEFORE LANGUAGE existed and
    // so defaulted to python, then runs the one-time `--data LANGUAGE=node`
    // correction, then gets swept like any other adopter with no flag at all.
    // The correction has to overwrite a recorded answer, not supply a missing one.
    corrected = mkdtempSync(join(tmpdir(), "sandcastle-node-corrected-"));
    const gadopt = initRepo(corrected);
    writeFileSync(join(corrected, "package.json"), '{ "name": "adopter" }\n');
    gadopt("add", "-A");
    gadopt("commit", "-q", "-m", "init adopter");
    execFileSync("copier", ["copy", "--defaults", "--vcs-ref", V1, src, corrected], {
      encoding: "utf8",
    });
    gadopt("add", "-A");
    gadopt("commit", "-q", "-m", "install sandcastle");
    asInstalled = answersIn(corrected);

    bump(gsrc, V2);
    correction = spawnSync(
      "copier",
      ["update", "--defaults", "--trust", "--vcs-ref", V2, "--data", "LANGUAGE=node"],
      { cwd: corrected, encoding: "utf8" }
    );
    gadopt("add", "-A");
    gadopt("commit", "-q", "-m", "correct LANGUAGE");

    bump(gsrc, V3);
    sweep = spawnSync("copier", ["update", "--defaults", "--trust", "--vcs-ref", V3], {
      cwd: corrected,
      encoding: "utf8",
    });
  });
  afterAll(() => discard(src, fresh, corrected));

  test("records LANGUAGE as node in the breadcrumb", () => {
    expect(answersIn(fresh)).toMatch(recordedAnswer("LANGUAGE", "node"));
  });

  test("is never asked for a Python version, so none is recorded", () => {
    expect(answersIn(fresh)).not.toMatch(/PYTHON_VERSION/);
  });

  // Guards the two below from passing vacuously: there is a recorded python
  // answer, and a recorded Python version, for the correction to overwrite.
  test("installs as python with a Python version before any correction", () => {
    expect(asInstalled).toMatch(recordedAnswer("LANGUAGE", "python"));
    expect(asInstalled).toMatch(/PYTHON_VERSION/);
  });

  test("the correction overwrites the recorded python answer", () => {
    expect(correction.status, correction.stderr).toBe(0);
    expect(answersIn(corrected)).toMatch(recordedAnswer("LANGUAGE", "node"));
  });

  test("the correction drops the Python version it had recorded as a python repo", () => {
    expect(answersIn(corrected)).not.toMatch(/PYTHON_VERSION/);
  });

  test("a later sweep passing no flag keeps the correction", () => {
    expect(sweep.status, sweep.stderr).toBe(0);
    expect(answersIn(corrected)).toMatch(recordedAnswer("LANGUAGE", "node"));
    expect(answersIn(corrected)).not.toMatch(/PYTHON_VERSION/);
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
