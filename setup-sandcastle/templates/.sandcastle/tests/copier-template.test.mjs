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
  symlinkSync,
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

// Any rendered file under the adopter's `.sandcastle/` subtree.
const renderedIn = (dir, file) => readFileSync(join(dir, ".sandcastle", file), "utf8");

const standardsIn = (dir) => renderedIn(dir, "CODING_STANDARDS.md");

// The marker rule renders on every arm — divergence happens in a Python adopter
// exactly as in a Node one — so both arms assert the same four things: the token
// spelled exactly, the counter-example that gives the reason test its teeth,
// adopter-ADDED files (which the review gate and the divergence report must
// agree about), and the clause that makes an unmarked edit a review failure.
const expectTheLocalMarkerRule = (doc) => {
  expect(doc).toContain("sandcastle:local");
  expect(doc).toMatch(/This repo is TypeScript/);
  expect(doc).toMatch(/add a new file/i);
  expect(doc).toMatch(/fails this axis/);
};

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
    // The render lands outside the dev home, where module resolution would find
    // neither the sandcastle lib nor @types/node — so the typecheck test below
    // needs this. Linked here rather than inside that test: a test that mutates
    // a fixture the whole block shares makes its neighbours order-dependent.
    symlinkSync(join(repoRoot, "setup-sandcastle", "node_modules"), join(target, "node_modules"));
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

  test("renders the sandcastle:local marker rule into the standards doc", () => {
    expectTheLocalMarkerRule(standardsIn(target));
  });

  // Parameterizing the orchestrator meant renaming `main.mts` and `address.mts`
  // to `.jinja`, which drops them out of the dev-home tsconfig's `*.mts` include
  // — so `npm run typecheck` stopped seeing 58 KB of the orchestrator. Typecheck
  // the RENDER instead: it is the same command an adopter runs (see SKILL.md),
  // and it covers the file as it will actually exist.
  //
  // Note the cost of where this lives: the whole block is skipped without copier
  // installed, so on such a machine nothing typechecks the orchestrator at all.
  // copier is a documented prereq of the skill, and the maintenance gate
  // (`npm run typecheck && npm test`) is run where it is installed.
  test("the rendered orchestrator typechecks", () => {
    const tsc = spawnSync("npx", ["tsc", "-p", ".sandcastle/tsconfig.json"], {
      cwd: target,
      encoding: "utf8",
    });
    expect(tsc.status, tsc.stdout + tsc.stderr).toBe(0);
  }, 60_000);

  // The commands are derived from LANGUAGE rather than asked, so the Python arm
  // needs the same proof the Node arm gets: the derived values are the justfile
  // recipes and `uv run pytest` this ecosystem actually has. The byte-identity
  // net next door proves these bytes did not move; this says what they mean.
  test("derives the justfile recipes and uv commands for a python adopter", () => {
    expect(renderedIn(target, "check-prompt.md")).toContain(
      'just check && echo "SANDCASTLE_CHECK: PASS"'
    );
    const prompt = renderedIn(target, "implement-prompt.md");
    expect(prompt).toContain("`just lint` and `just typecheck`");
    expect(prompt).toContain("uv run pytest <files>");
    for (const file of ["main.mts", "address.mts"]) {
      expect(renderedIn(target, file), file).toContain('[".venv"]');
    }
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
// The live prompt drawer now carries both styles for real — `implement-prompt`
// and `check-prompt` render `[[ CHECK_COMMAND ]]` while their `{{TASK_ID}}` and
// `{{MERGE_HEAD}}` placeholders must survive untouched — but a probe still earns
// its place: it isolates the delimiter behaviour to one throwaway `.jinja` that
// fails on `_envops` alone, rather than only when a real prompt happens to
// exercise both styles. It renders through the real `copier.yml`.
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

// Files an arc ticket deliberately APPENDS to. Listing one relaxes the promise
// from "identical" to "the pre-arc body, still byte-for-byte, plus new text at
// the end" — so the rest of the file stays pinned. Re-pinning PRE_ARC instead
// would exempt every file at once and retire the net for the tickets to come.
//   .sandcastle/CODING_STANDARDS.md — the sandcastle:local rule (issue #136)
const ARC_APPENDED_RENDERS = [".sandcastle/CODING_STANDARDS.md"];

// Comment text an arc ticket deliberately REWRITES in place. Each pair is
// applied to the pre-arc body before the diff, so the rewrite is spelled out
// here and every other byte of the file stays pinned — the same bargain as
// ARC_APPENDED_RENDERS, for an edit rather than an append. A pair that no longer
// matches fails too, so a stale declaration cannot sit here excusing nothing.
//   .sandcastle/main.mts — the two copyToWorktree comments went neutral (#135).
//   The value under them now branches by ecosystem and supplies the specifics
//   the prose dropped, which is why the comments did not branch as well.
const ARC_REWRITTEN_PROSE = {
  ".sandcastle/main.mts": [
    [
      "// Copy the host's virtualenv into the worktree before each sandbox starts.\n" +
        "// Avoids resolving+downloading every dependency from scratch; sandboxConfig's\n" +
        "// `uv sync` hook reconciles anything added since the copy.",
      "// Copy the host's installed dependencies into the worktree before each sandbox\n" +
        "// starts. Avoids resolving+downloading every dependency from scratch;\n" +
        "// sandboxConfig's install hook reconciles anything added since the copy.",
    ],
    [
      "copyToWorktree, // seed .venv so `just check` reuses deps, no re-resolve",
      "copyToWorktree, // seed the deps so the check reuses them, no re-resolve",
    ],
  ],
  // .sandcastle/Dockerfile — the header's ecosystem clause branches (#134), but
  // the two lines that only mention a toolchain in passing went neutral instead:
  // the Node arm's image carries neither uv nor just, and a comment must not
  // claim layers the file no longer renders.
  ".sandcastle/Dockerfile": [
    [
      "# and the target's uv/just toolchain. main.mts runs on the HOST (via tsx) — it\n" +
        "# is never in this image; only the in-sandbox agent + its tools live here.",
      "# and the target's toolchain. main.mts runs on the HOST (via tsx) — it is never\n" +
        "# in this image; only the in-sandbox agent + its tools live here.",
    ],
    [
      "# uv + claude both install under ~/.local/bin",
      "# The tools installed above land under ~/.local/bin",
    ],
  ],
  // .sandcastle/sandbox-identity.mts — `ruff/ty` names Python linters and nothing
  // else, so this one had no substitute to reach for and went neutral (#146).
  ".sandcastle/sandbox-identity.mts": [
    [
      " * Phase-3 `just check` gate runs the same ruff/ty.",
      " * Phase-3 check gate runs the same linters anyway.",
    ],
  ],
  // .sandcastle/review-verdict.mts — both comments describe the gate WRAPPER,
  // whose command is rendered from CHECK_COMMAND next door in check-prompt.md.
  // Naming the recipe here would have meant templating a module 222 lines of
  // dev tests import by name, for comment prose — so they point at the rendered
  // command instead of repeating it (#146).
  ".sandcastle/review-verdict.mts": [
    [
      "// over `just check` (lint + typecheck + the whole test suite) and fails CLOSED:",
      "// over the repo's check gate (lint + typecheck + the whole test suite) and fails\n// CLOSED:",
    ],
    [
      "// The gate wrapper echoes this sentinel only when `just check` exits zero\n" +
        "// (`just check && echo SANDCASTLE_CHECK: PASS`). No sentinel → not green → fail\n" +
        "// closed. Host-coupled contract string (see CODING_STANDARDS) — don't reword.",
      "// The gate wrapper echoes this sentinel only when the repo's check command exits\n" +
        "// zero (`… && echo SANDCASTLE_CHECK: PASS`, rendered into check-prompt.md). No\n" +
        "// sentinel → not green → fail closed. Host-coupled contract string (see\n" +
        "// CODING_STANDARDS) — don't reword.",
    ],
  ],
  // .sandcastle/sandbox-identity.check.mts — the header named `just check` to
  // explain why the check runs under tsx (#146). The reason survives the
  // rewrite; only the Python-only recipe name goes.
  ".sandcastle/sandbox-identity.check.mts": [
    [
      "// Self-check for applyBotToken — no test runner in this repo (package.json\n" +
        '// "test" is a stub, `just check` is Python-only), so this runs via `npx tsx`.\n' +
        "//   npx tsx .sandcastle/sandbox-identity.check.mts",
      "// Self-check for applyBotToken — no test runner ships inside `.sandcastle/`, so\n" +
        "// this runs via `npx tsx`:\n" +
        "//   npx tsx .sandcastle/sandbox-identity.check.mts",
    ],
  ],
};

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
      if (ARC_APPENDED_RENDERS.includes(path)) {
        expect(is.get(path)?.startsWith(body), `${path} changed above the appended text`).toBe(true);
        continue;
      }
      let expected = body;
      for (const [from, to] of ARC_REWRITTEN_PROSE[path] ?? []) {
        expect(expected, `${path}: declared rewrite no longer matches the pre-arc text`).toContain(
          from
        );
        expected = expected.replace(from, to);
      }
      expect(is.get(path), path).toBe(expected);
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
  let twin;
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

    // The same template on the other arm, so a test can compare the two renders
    // directly — the only way to catch prose that was forked per ecosystem
    // rather than parameterized.
    twin = mkdtempSync(join(tmpdir(), "sandcastle-node-twin-"));
    execFileSync("copier", ["copy", "--defaults", "--vcs-ref", V1, src, twin], {
      encoding: "utf8",
    });

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

  test("gets the sandcastle:local marker rule too — it is not a python-arm rule", () => {
    expectTheLocalMarkerRule(standardsIn(fresh));
  });

  test("is never asked for a Python version, so none is recorded", () => {
    expect(answersIn(fresh)).not.toMatch(/PYTHON_VERSION/);
  });

  // The gate agent runs this line verbatim and the orchestrator gates the PR on
  // the sentinel it prints, so a `just check` here is not a cosmetic wrong word:
  // a Node repo has no justfile and the gate would fail before running anything.
  // The implementer runs these before every commit, so a wrong name here costs
  // the feedback loop entirely: the agent's fast check errors instead of running.
  test("the per-commit fast check names npm commands", () => {
    const prompt = renderedIn(fresh, "implement-prompt.md");
    expect(prompt).toContain("npm run lint");
    expect(prompt).toContain("npm run typecheck");
    expect(prompt).not.toMatch(/just (check|lint|typecheck)/);
    expect(prompt).not.toContain("uv run pytest");
  });

  // `npm run test <files>` drops the file list — npm needs a `--` separator to
  // forward arguments — so the "scoped" check would silently run everything.
  // `npx vitest run <files>` forwards them, which is why the arm names it.
  test("the scoped test command forwards its file arguments", () => {
    const prompt = renderedIn(fresh, "implement-prompt.md");
    expect(prompt).toContain("npx vitest run <files>");
    expect(prompt).not.toMatch(/npm run test <files>/);
  });

  // The discipline the paragraph teaches — map changed paths to their tests,
  // include when unsure, the full suite is not the per-commit gate — is
  // ecosystem-neutral and must stay single-source. Blanking the four commands
  // out of each arm should leave two byte-identical paragraphs; if a ticket ever
  // forks the prose per ecosystem, this is what disagrees.
  test("says the same thing on both arms once the commands are blanked", () => {
    const blank = (text) =>
      text.replace(
        /npm run lint && npm run typecheck && npm run test|just check|npm run lint|just lint|npm run typecheck|just typecheck|npx vitest run <files>|uv run pytest <files>/g,
        "<cmd>"
      );
    expect(blank(renderedIn(fresh, "implement-prompt.md"))).toBe(
      blank(renderedIn(twin, "implement-prompt.md"))
    );
  });

  // The orchestrator copies the host's dependency cache into each worktree so a
  // sandbox reuses it instead of resolving from scratch. `.venv` does not exist
  // in a Node repo, so the copy would be a silent no-op and every sandbox would
  // pay a full `npm install`. The comments beside these values are asserted too:
  // a neutral rewrite is the whole reason they were not branched.
  test("seeds node_modules into each worktree, and says nothing Python beside it", () => {
    for (const file of ["main.mts", "address.mts"]) {
      const src = renderedIn(fresh, file);
      expect(src, file).toContain('["node_modules"]');
      expect(src, file).not.toMatch(/\.venv|\buv\b|pytest/);
    }
  });

  // The gate prompt is not the only place the check command is spoken aloud: the
  // orchestrator quotes it back in the comment it posts when a set fails, and the
  // address-comments prompt tells its agent to run it. An agent handed a recipe
  // its repo does not have follows the instruction and fails.
  test("names no justfile recipe anywhere it tells an agent what to run", () => {
    for (const file of ["main.mts", "address-comments-prompt.md"]) {
      expect(renderedIn(fresh, file), file).not.toMatch(/just (check|lint|typecheck)/);
    }
  });

  test("the check-gate runs npm scripts, not a justfile recipe", () => {
    const gate = renderedIn(fresh, "check-prompt.md");
    expect(gate).toContain(
      'npm run lint && npm run typecheck && npm run test && echo "SANDCASTLE_CHECK: PASS"'
    );
    expect(gate).not.toContain("just check");
  });

  // The two places the ecosystems genuinely differ in the image. Everything else
  // in the Dockerfile — apt deps, the gh block, the UID/GID args, the Claude CLI,
  // PATH, WORKDIR, ENTRYPOINT — stays shared, which the byte-identity net next
  // door holds to on the Python side.
  test("builds on a Node base, and the Python arm still on Debian", () => {
    expect(renderedIn(fresh, "Dockerfile")).toMatch(/^FROM node:22-bookworm$/m);
    expect(renderedIn(twin, "Dockerfile")).toMatch(/^FROM debian:bookworm-slim$/m);
  });

  // The Node base image already ships a `node` user at 1000:1000, so `groupadd`
  // and `useradd` would collide with it — this arm renames instead. The rename
  // has to carry `-n agent` for the GROUP too: without it the container reports
  // `gid=1000(node)` while the Python arm yields `gid=1000(agent)`, and the two
  // ecosystems hand the orchestrator different identities inside the sandbox.
  test("renames the base image's user and its group to agent", () => {
    const dockerfile = renderedIn(fresh, "Dockerfile");
    expect(dockerfile).toContain("groupmod -o -g $AGENT_GID -n agent node");
    expect(dockerfile).toMatch(/usermod .*-l agent node/);
    expect(dockerfile).not.toMatch(/groupadd|useradd/);
  });

  // `node` and `npm` ship with the base image and the derived commands are npm
  // scripts, so this arm needs no extra toolchain — and carrying uv, a baked
  // interpreter and a task runner a Node repo never invokes is three image
  // layers of dead weight. The prose goes with them: nothing left in the file
  // may claim a uv/just toolchain on an image that has neither.
  test("installs no uv, no interpreter and no just, and claims none", () => {
    const dockerfile = renderedIn(fresh, "Dockerfile");
    expect(dockerfile).not.toMatch(/\buv\b|PYTHON_VERSION|rust-just|\bjust\b/);
    // Not vacuous: the shared layers this arm keeps are still there.
    expect(dockerfile).toContain("apt-get install -y gh");
    expect(dockerfile).toContain("https://claude.ai/install.sh");
  });

  // Every sandbox runs this hook the moment it comes up. `uv sync` does not
  // exist on a Node image, so an unbranched hook means every sandbox starts with
  // a failed hook and no installed dependencies — the counterpart to the
  // `node_modules` #135 seeds into the worktree.
  test("installs dependencies with npm, not uv", () => {
    const identity = renderedIn(fresh, "sandbox-identity.mts");
    expect(identity).toContain('{ command: "npm install" }');
    expect(identity).not.toContain("uv sync");
  });

  // uv's own variable, telling it where to put the virtualenv. npm has no idea
  // what it means, so on this arm it is a dead env var pointing at a directory
  // that never exists.
  test("sets no UV_PROJECT_ENVIRONMENT, and the Python arm still does", () => {
    expect(renderedIn(fresh, "sandbox-identity.mts")).not.toContain("UV_PROJECT_ENVIRONMENT");
    expect(renderedIn(twin, "sandbox-identity.mts")).toContain(
      'UV_PROJECT_ENVIRONMENT: "/home/agent/.venv"'
    );
  });

  // A sweep rather than a file list. The two ticketed sites (#135, #146) were
  // each found by reading, and reading is what misses the next one — a file
  // added later inherits this check for free. The Dockerfile is out of scope by
  // construction: it is the one place naming a toolchain is the point, and its
  // arms are asserted directly.
  test("no rendered file names Python tooling anywhere outside the Dockerfile", () => {
    const python = /\buv\b|\.venv|pytest|\bruff\b|just (check|lint|typecheck)/;
    const offenders = [];
    for (const [path, body] of renderedTree(join(fresh, ".sandcastle"))) {
      if (path === "Dockerfile") continue;
      for (const [i, line] of body.split("\n").entries()) {
        if (python.test(line)) offenders.push(`${path}:${i + 1}: ${line.trim()}`);
      }
    }
    expect(offenders).toEqual([]);
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
