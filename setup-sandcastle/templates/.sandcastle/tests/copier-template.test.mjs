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
import { hasCopier, renderPythonArm } from "./render-fixture.mjs";

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

// The formatting rule (issue #183) renders on every arm too — a Python adopter's
// formatter reflows a rendered file exactly as a Node one's does. Both arms
// assert the instruction (exclude the subtree from the formatter) and both
// consequences the rule exists to name: unmarked divergence now, and a merge
// conflict on the next template update.
const expectTheFormattingRule = (doc) => {
  expect(doc).toMatch(/formatter/i);
  // `[\s\S]` rather than `.` — the doc is wrapped prose, so the instruction and
  // the path it names routinely land on different lines.
  expect(doc).toMatch(/exclude[\s\S]{0,40}\.sandcastle/i);
  // "divergence report", not bare "divergence" — rule 5 already says the latter,
  // so the loose word would pass with rule 6 deleted.
  expect(doc).toMatch(/divergence\s+report/i);
  expect(doc).toMatch(/conflict/i);
};

// Answers are matched line-anchored. A bare substring would also match a value
// commented out, indented under another key, or prefixing a longer line.
const recordedAnswer = (name, value) =>
  new RegExp(`^${name}: ['"]?${value.replace(".", "\\.")}['"]?$`, "m");

// copier is a documented install-time prereq (`uv tool install copier`); on a
// machine without it, skip rather than fail a red the env can't turn green.
describe.skipIf(!hasCopier())("copier copy renders the orchestrator at the git root", () => {
  let target;
  beforeAll(() => {
    // The subproject root is the target's git root; render straight into it and
    // `.sandcastle/` lands as a subtree. Source is the repo root (a git root),
    // no --vcs-ref: copier renders the working tree AND records `_commit` from
    // the source's HEAD, so the test runs against uncommitted template edits and
    // still proves version pinning. `node_modules` is linked here rather than
    // inside the typecheck test: a test that mutates a fixture the whole block
    // shares makes its neighbours order-dependent.
    target = renderPythonArm(repoRoot, { linkModules: true });
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

  // A render carries what an adopter RUNS. The domain model and the ADRs behind
  // it are maintainer reading, and the self-check is a developer's — all three
  // keep their home in this repo, and none of them ships (#182).
  test("withdraws the maintainer docs and the self-check from the render", () => {
    for (const path of ["CONTEXT.md", "docs", "sandbox-identity.check.mts"]) {
      expect(existsSync(join(target, ".sandcastle", path)), path).toBe(false);
    }
  });

  // The counterweight, and the reason "looks like documentation" is the wrong
  // test: each of these has a named runtime reader — the review verdict module
  // and the standards judge load the standards, the token-minting script names
  // bot-setup.md in the error it prints, and an adopter typechecks the
  // orchestrator with that tsconfig.
  test("keeps the documentation a runtime reader actually loads", () => {
    for (const path of ["CODING_STANDARDS.md", "bot-setup.md", "tsconfig.json"]) {
      expect(existsSync(join(target, ".sandcastle", path)), path).toBe(true);
    }
  });

  test("renders the PYTHON_VERSION answer into the Dockerfile", () => {
    const dockerfile = readFileSync(join(target, ".sandcastle", "Dockerfile"), "utf8");
    expect(dockerfile).toMatch(/^ARG PYTHON_VERSION=3\.14$/m);
  });

  test("renders the sandcastle:local marker rule into the standards doc", () => {
    expectTheLocalMarkerRule(standardsIn(target));
  });

  test("renders the formatting rule into the standards doc", () => {
    expectTheFormattingRule(standardsIn(target));
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

  // Sandcastle forwards `.sandcastle/.env` into sandboxes as a FILE and never
  // into the host process — until main.mts's loadEnvFile, which pulls EVERY key
  // into the host so sandboxIdentity() can see GITHUB_APP_*. `gh` prefers an env
  // token over ~/.config/gh, so a GH_TOKEN dragged along shadows the working
  // keyring credential and 401s every host-side gh call. Dropping that one key
  // restores what the load broke, and .env.example says so where the operator
  // reads it (issue #155).
  test("drops GH_TOKEN from the host process, and .env.example says why", () => {
    expect(renderedIn(target, "main.mts")).toContain("delete process.env.GH_TOKEN;");
    expect(renderedIn(target, ".env.example")).toMatch(/deletes it host-side/);
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
//   .sandcastle/CODING_STANDARDS.md — the sandcastle:local rule (issue #136) and
//   the formatting rule below it (issue #183)
const ARC_APPENDED_RENDERS = [".sandcastle/CODING_STANDARDS.md"];

// Text deliberately REWRITTEN in place since the pin — comment prose from an
// arc ticket, or code where a fix has to change what renders. Each pair is
// applied to the pre-arc body before the diff, so the rewrite is spelled out
// here and every other byte of the file stays pinned — the same bargain as
// ARC_APPENDED_RENDERS, for an edit rather than an append. A pair that no longer
// matches fails too, so a stale declaration cannot sit here excusing nothing.
//   .sandcastle/main.mts — the two copyToWorktree comments went neutral (#135).
//   The value under them now branches by ecosystem and supplies the specifics
//   the prose dropped, which is why the comments did not branch as well.
// A withdrawn file needs no entry here: the render has no counterpart to compare
// it against, so the set net owns it alone. That is why #127's CONTEXT.md rewrite
// and #146's self-check header no longer appear — both files left the render.
const ARC_REWRITTEN_PROSE = {
  // .sandcastle/base-resolution.mts — #127, a fix rather than an arc ticket: a
  // parent's ISSUE STATE now gates liveness ahead of its branch content, and a
  // new export names the closed issues' branches for the sweep to delete.
  ".sandcastle/base-resolution.mts": [
    [
      "// on, emitted by the planner) plus one fact about each parent: does its issue\n" +
        "// branch exist locally with work not already in `main`?",
      "// on, emitted by the planner) plus two facts about each parent: is its issue\n" +
        "// still open, and does its branch exist locally with work not already in `main`?\n" +
        "// Both must hold for the parent to count as live work — see `isLiveParent`.",
    ],
    [
      "  branchExistsWithWork: (parentId: string) => boolean;\n" +
        "  // Invoked for the ≥2-parent (diamond) case.",
      "  branchExistsWithWork: (parentId: string) => boolean;\n" +
        "  // True when the parent's ISSUE is closed — see `isLiveParent`. Required, not\n" +
        "  // optional: a default would silently restore the content-only liveness that\n" +
        "  // #127 exists to end.\n" +
        "  issueIsClosed: (parentId: string) => boolean;\n" +
        "  // Invoked for the ≥2-parent (diamond) case.",
    ],
    [
      "// Resolve the base ref an issue's branch should be cut from",
      "// Is a parent's branch live work to build on? Two questions, and the issue's\n" +
        "// state is asked first (issue #127). A closed issue's branch can still carry\n" +
        "// commits absent from `main`: #101 shipped as a from-scratch reimplementation,\n" +
        "// so nothing on main matched `ff2f3b6` by content and `git cherry` / patch-id\n" +
        "// had nothing to match. Content alone cannot tell a superseded implementation\n" +
        "// from a live one — it looks identical to \"unmerged work\" — so a branch of a\n" +
        "// closed issue is dead by definition, whatever its commits say.\n" +
        "const isLiveParent = (\n" +
        "  parentId: string,\n" +
        "  branchExistsWithWork: (id: string) => boolean,\n" +
        "  issueIsClosed: (id: string) => boolean\n" +
        "): boolean => !issueIsClosed(parentId) && branchExistsWithWork(parentId);\n" +
        "\n" +
        "// Resolve the base ref an issue's branch should be cut from",
    ],
    [
      "  branchExistsWithWork,\n  onMultiParent = () => \"main\",",
      "  branchExistsWithWork,\n" +
        "  issueIsClosed,\n" +
        '  onMultiParent = () => "main",',
    ],
    [
      '    return branchExistsWithWork(parent) ? issueBranch(parent) : "main";',
      "    return isLiveParent(parent, branchExistsWithWork, issueIsClosed)\n" +
        "      ? issueBranch(parent)\n" +
        '      : "main";',
    ],
    [
      "  branchExistsWithWork: (parentId: string) => boolean;\n}",
      "  branchExistsWithWork: (parentId: string) => boolean;\n" +
        "  // Whether a parent's ISSUE is closed — see `isLiveParent`. Required, as above.\n" +
        "  issueIsClosed: (parentId: string) => boolean;\n}",
    ],
    [
      "  { git, branchExistsWithWork }: MultiParentDeps\n" +
        "): string | null {\n" +
        "  const present = parents.filter(branchExistsWithWork).map(issueBranch);",
      "  { git, branchExistsWithWork, issueIsClosed }: MultiParentDeps\n" +
        "): string | null {\n" +
        "  const present = parents\n" +
        "    .filter((p) => isLiveParent(p, branchExistsWithWork, issueIsClosed))\n" +
        "    .map(issueBranch);",
    ],
    [
      "  git(`worktree remove --force ${wt}`);\n  return ok ? baseBranch : null;\n}",
      "  git(`worktree remove --force ${wt}`);\n" +
        "  return ok ? baseBranch : null;\n" +
        "}\n" +
        "\n" +
        "// The other half of #127: stop the landmine being laid at all. Given the output\n" +
        "// of `git for-each-ref --format=%(refname:short) refs/heads/sandcastle/issue-*`,\n" +
        "// name the branches whose issue is closed — the sweep deletes them, so no later\n" +
        "// diamond can find a shipped issue's branch and read it as live work.\n" +
        "//\n" +
        "// Local refs only, and only `sandcastle/issue-<n>`: the scratch `base-*`/`pr-*`\n" +
        "// branches share the prefix but carry no issue id, and an id that does not parse\n" +
        '// must never be looked up as issue "" and deleted on the answer.\n' +
        "export function staleClosedBranches(\n" +
        "  refListing: string | null,\n" +
        "  issueIsClosed: (issueId: string) => boolean\n" +
        "): string[] {\n" +
        '  return (refListing ?? "")\n' +
        '    .split("\\n")\n' +
        "    .map((line) => line.trim())\n" +
        "    .filter((branch) => /^sandcastle\\/issue-\\d+$/.test(branch))\n" +
        '    .filter((branch) => issueIsClosed(branch.slice("sandcastle/issue-".length)));\n' +
        "}",
    ],
  ],
  // .sandcastle/.env.example — #155 lifts visual-teach's GH_TOKEN note upstream.
  // The adopter's wording ("LEGACY — leave blank", key commented out) says what is
  // true THERE, where the bot App is already running; upstream it would strand a
  // fresh adopter, for whom GH_TOKEN is still the only path until bot-setup.md is
  // done. So the key stays live and the note keeps the two portable facts: blank
  // it once the bot works, and main.mts drops it host-side either way.
  ".sandcastle/.env.example": [
    [
      "# Required repository permissions: Issues (Read and write) and Metadata (Read)\nGH_TOKEN=",
      "# Required repository permissions: Issues (Read and write) and Metadata (Read)\n" +
        "# Fallback only — the bot App below supersedes it. Once the bot works, blank this\n" +
        "# line (bot-setup.md, end of Step 5) so runs can't attribute to your personal\n" +
        "# account. main.mts deletes it host-side either way, so a stale value here cannot\n" +
        "# shadow your ~/.config/gh credential; sandboxes still read it from this file.\n" +
        "GH_TOKEN=",
    ],
  ],
  ".sandcastle/main.mts": [
    // #127's orchestrator half: the closed-issue lookup base resolution now asks,
    // the GC that deletes those issues' branches, and the two call sites.
    [
      '  buildMultiParentBase,\n} from "./base-resolution.mts";',
      "  buildMultiParentBase,\n" +
        "  staleClosedBranches,\n" +
        '} from "./base-resolution.mts";',
    ],
    [
      "// Whether `branch` still merges into main without conflict.",
        "// Issue ids GitHub reports as CLOSED. Base resolution asks this before trusting\n" +
        "// what a parent branch's commits look like (issue #127), and the branch\n" +
        "// GC below asks it to clear the branches of shipped issues. Memoised over one\n" +
        "// fetch: the answer is read once per parent per issue per iteration, and the bot\n" +
        "// never closes an issue mid-run.\n" +
        "let closedIds: Set<string> | null = null;\n" +
        "function issueIsClosed(id: string): boolean {\n" +
        "  if (closedIds === null) {\n" +
        "    const rows = fetchIssueEdges();\n" +
        "    if (rows === null) {\n" +
        "      // Fail OPEN (an empty set): liveness falls back to branch content, the\n" +
        "      // pre-#127 behaviour. Failing closed would call every parent dead and base\n" +
        "      // the whole forest on main \u2014 a wrong answer for every issue, to avoid a\n" +
        "      // wrong answer for one.\n" +
        "      console.error(\n" +
        "        \"  ! could not list issue states; base resolution falls back to branch content this run\"\n" +
        "      );\n" +
        "    }\n" +
        "    closedIds = new Set(\n" +
        "      (rows ?? [])\n" +
        "        .filter((row) => row.state === \"CLOSED\")\n" +
        "        .map((row) => String(row.number))\n" +
        "    );\n" +
        "  }\n" +
        "  return closedIds.has(id);\n" +
        "}\n" +
        "\n" +
        "// Delete the local `sandcastle/issue-<n>` branches of closed issues, once per\n" +
        "// run before any branch is cut. A closed issue's branch has no reader left: its\n" +
        "// work either landed or was superseded, and leaving it on disk is what let a\n" +
        "// diamond merge #101's dead implementation into #107's base every run (#127).\n" +
        "// Local only \u2014 deleting a remote branch is a human's call, and base resolution\n" +
        "// reads local refs anyway.\n" +
        "function gcClosedIssueBranches(): void {\n" +
        "  const stale = staleClosedBranches(\n" +
        "    git(`for-each-ref --format=%(refname:short) refs/heads/sandcastle/issue-*`),\n" +
        "    issueIsClosed\n" +
        "  );\n" +
        "  for (const branch of stale) {\n" +
        "    // Only claim the delete git actually did: `branch -D` fails when the branch\n" +
        "    // is checked out in a leftover worktree, and a log line saying otherwise\n" +
        "    // would hide the exact landmine this GC exists to clear.\n" +
        "    if (git(`branch -D ${branch}`) === null) {\n" +
        "      console.error(`  ! ${branch} \u2014 issue closed but the branch would not delete`);\n" +
        "    } else {\n" +
        "      console.log(`  ${branch} \u2014 issue closed; stale branch deleted`);\n" +
        "    }\n" +
        "  }\n" +
        "}\n" +
        "\n" +
        "// Whether `branch` still merges into main without conflict.",
    ],
    [
      "// Open parents whose every sub-issue is closed: the spec is delivered and only\n" +
        "// its umbrella issue lingers. The bot never closes an issue, so the run summary\n" +
        "// surfaces these for a human to close (spent-parent hygiene).\n" +
        "function getDeliveredParents(): Set<string> {\n" +
        "  // ponytail: --state all spans every closed issue, so the limit is higher than\n" +
        "  // the open-only fetches. gh returns newest-first, and a spec's children sit\n" +
        "  // near it in numbering, so truncation rarely splits a family. If it ever does\n" +
        "  // (a repo past the cap), the flag can be wrong in either direction \u2014 this is a\n" +
        "  // human-verified close reminder, not an auto-close, so the harm is a stray\n" +
        "  // suggestion. Raise the limit if that ceiling bites.\n" +
        "  const out = gh(\n" +
        "    `issue list --state all --limit 1000 --json number,state,parent --jq '[.[] | {number, state, parent: .parent.number}]'`\n" +
        "  );\n" +
        "  if (!out) return new Set<string>();\n" +
        "  return deliveredParentIds(issueEdgeRowsSchema.parse(JSON.parse(out)));\n" +
        "}",
        "// Every issue's id, state and parent \u2014 the one query behind both the closed-set\n" +
        "// `issueIsClosed` memoises (#127) and the spent-parent check below. Null when the\n" +
        "// query fails; each caller decides what that means for it.\n" +
        "//\n" +
        "// ponytail: --state all spans every closed issue, so the limit is higher than\n" +
        "// the open-only fetches. gh returns newest-first, and a spec's children sit\n" +
        "// near it in numbering, so truncation rarely splits a family. If it ever does\n" +
        "// (a repo past the cap), the flag can be wrong in either direction \u2014 this is a\n" +
        "// human-verified close reminder, not an auto-close, so the harm is a stray\n" +
        "// suggestion. Raise the limit if that ceiling bites.\n" +
        "function fetchIssueEdges(): z.infer<typeof issueEdgeRowsSchema> | null {\n" +
        "  const out = gh(\n" +
        "    `issue list --state all --limit 1000 --json number,state,parent --jq '[.[] | {number, state, parent: .parent.number}]'`\n" +
        "  );\n" +
        "  return out ? issueEdgeRowsSchema.parse(JSON.parse(out)) : null;\n" +
        "}\n" +
        "\n" +
        "// Open parents whose every sub-issue is closed: the spec is delivered and only\n" +
        "// its umbrella issue lingers. The bot never closes an issue, so the run summary\n" +
        "// surfaces these for a human to close (spent-parent hygiene). Fetched fresh at\n" +
        "// the end of the run rather than reusing the start-of-run memo, so an issue a\n" +
        "// human closed mid-run is counted.\n" +
        "function getDeliveredParents(): Set<string> {\n" +
        "  return deliveredParentIds(fetchIssueEdges() ?? []);\n" +
        "}",
    ],
    [
      "// Pre-loop reconciliation sweep: restore in-review ⟺ open PR invariant before",
      "// Before the sweep, and before any branch is cut this run: clear the branches of\n" +
        "// closed issues, so nothing downstream can mistake shipped work for live work.\n" +
        'console.log("\\n=== Stale branch GC: closed issues ===\\n");\n' +
        "gcClosedIssueBranches();\n" +
        "\n" +
        "// Pre-loop reconciliation sweep: restore in-review ⟺ open PR invariant before",
    ],
    [
      "        branchExistsWithWork,\n" +
        "        onMultiParent: (ps) =>\n" +
        "          buildMultiParentBase(issue.id, ps, { git, branchExistsWithWork }),",
      "        branchExistsWithWork,\n" +
        "        issueIsClosed,\n" +
        "        onMultiParent: (ps) =>\n" +
        "          buildMultiParentBase(issue.id, ps, {\n" +
        "            git,\n" +
        "            branchExistsWithWork,\n" +
        "            issueIsClosed,\n" +
        "          }),",
    ],
    // #155, the other half of the same fix: the host-side `delete`, upstreamed
    // from visual-teach because nothing in it names that repo.
    [
      'if (existsSync(".sandcastle/.env")) process.loadEnvFile(".sandcastle/.env");',
      'if (existsSync(".sandcastle/.env")) process.loadEnvFile(".sandcastle/.env");\n' +
        "\n" +
        "// …but not GH_TOKEN. The load above pulls EVERY key into the HOST process, and\n" +
        "// `gh` prefers an env token over ~/.config/gh — so a stale GH_TOKEN in .env\n" +
        "// shadows the working keyring credential and 401s every host-side gh call.\n" +
        "// Dropping it restores what the load broke: sandboxes still get their token,\n" +
        "// either from sandboxIdentity()'s minted App token or from the .env FILE\n" +
        "// Sandcastle forwards independently of process.env.\n" +
        "delete process.env.GH_TOKEN;",
    ],
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
    // The three below are #169, a fix rather than an arc ticket: the outcome
    // kind `spec-fail` reported a standards-only failure as a spec failure, so
    // it became `review-fail` and now carries the axes that actually failed.
    [
      "// sole writer — gets targeted context. Route through the existing\n" +
        "            // spec-fail path (shared REVIEW_RETRY_CAP; escalates to",
      "// sole writer — gets targeted context. Route through the review-fail\n" +
        "            // path (both axes share one REVIEW_RETRY_CAP; escalates to",
    ],
    [
      'return { issue, kind: "spec-fail" as const };',
      "return {\n" +
        "              issue,\n" +
        '              kind: "review-fail" as const,\n' +
        "              failedAxes: combined.failedAxes,\n" +
        "            };",
    ],
    [
      "const plan = planOutcomeTransition({ kind, issue, attempts });",
      "// Only a review-fail outcome carries failedAxes; narrow before reading it.\n" +
        "    const failedAxes =\n" +
        '      outcome.status === "fulfilled" && "failedAxes" in outcome.value\n' +
        "        ? outcome.value.failedAxes\n" +
        "        : undefined;\n" +
        "    const plan = planOutcomeTransition({ kind, issue, attempts, failedAxes });",
    ],
    // Two ADR pointers, dropped with the ADRs themselves (#182). What each
    // comment explains stays; only the citation an adopter cannot follow goes.
    [
      "// tested planRetention (ADR-0002).",
      "// tested planRetention.",
    ],
    [
      "planOutcomeTransition's call (#102, ADR-0002); this",
      "planOutcomeTransition's call (#102); this",
    ],
    // #103: the set-level fold moved out to retry-policy.mts, so the import
    // follows it and the inline block collapses to the one call.
    [
      '  recordAttempt,\n} from "./retry-policy.mts";',
      '  recordSetAttempt,\n} from "./retry-policy.mts";',
    ],
    [
      "    // Consecutive gate-failure cap (#25): count one failure per issue under key\n" +
        '    // gate-<id>. A real "test-fail" increments and may escalate at the cap; a\n' +
        '    // "harness-error" is an infra fault and is NEVER counted (it can\'t retire a\n' +
        '    // good set); a "pass" clears the counter so the cap is CONSECUTIVE failures.\n' +
        "    // The set fails and passes the gate in lockstep, so all its gate-<id>\n" +
        "    // counters move together and escalate on the same iteration.\n" +
        "    let escalated = false;\n" +
        "    {\n" +
        "      let gateAttempts = readAttempts();\n" +
        '      if (verdict.status === "pass") {\n' +
        "        for (const id of gateIds) delete gateAttempts[`gate-${id}`];\n" +
        '      } else if (verdict.status === "test-fail") {\n' +
        "        for (const id of gateIds) {\n" +
        "          const r = recordAttempt(gateAttempts, `gate-${id}`);\n" +
        "          gateAttempts = r.attempts;\n" +
        "          // OR-reduce, not last-wins: the set escalates if ANY member hit the\n" +
        "          // cap. In lockstep every gate-<id> escalates together, but recordAttempt\n" +
        "          // deletes a key when it escalates, so were the counters ever out of step\n" +
        "          // a last-wins read could miss an escalation and loop the set forever.\n" +
        "          escalated ||= r.escalate;\n" +
        "        }\n" +
        "      }\n" +
        "      writeAttempts(gateAttempts);\n" +
        "    }\n" +
        "\n" +
        "    const plan = planGateOutcome(verdict, gateIds, escalated);",
      "    // Consecutive gate-failure cap (#25): one counter per issue under key\n" +
        "    // gate-<id>, folded by recordSetAttempt — which owns what each verdict does\n" +
        "    // to the counters and when the set escalates (#103).\n" +
        "    const counters = recordSetAttempt(\n" +
        "      readAttempts(),\n" +
        "      gateIds.map((id) => `gate-${id}`),\n" +
        "      verdict.status\n" +
        "    );\n" +
        "    writeAttempts(counters.attempts);\n" +
        "\n" +
        "    const plan = planGateOutcome(verdict, gateIds, counters.escalated);",
    ],
    // #104 moved every `gh` JSON parser into github-parse.mts and put one
    // failure policy behind them, so the call sites below shrank to the fetch
    // plus a named parser, and the three inline result limits became two
    // shared constants.
    [
      "import { parseOpenIssues, parsePrsClosingIssues } from \"./github-parse.mts\";",
      "import {\n" +
        "  ALL_ISSUE_LIMIT,\n" +
        "  OPEN_ISSUE_LIMIT,\n" +
        "  parseBlockedByRows,\n" +
        "  parseIssueEdges,\n" +
        "  parseIssueList,\n" +
        "  parseOpenIssues,\n" +
        "  parseParentEdges,\n" +
        "  parsePrsClosingIssues,\n" +
        "  type IssueEdgeRow,\n" +
        "} from \"./github-parse.mts\";",
    ],
    [
      "  const out = gh(\n" +
        "    `issue list --state open --label \"${label}\" --limit 100 --json number,title`\n" +
        "  );\n" +
        "  return out ? JSON.parse(out) : [];",
      "  return parseIssueList(\n" +
        "    gh(\n" +
        "      `issue list --state open --label \"${label}\" --limit ${OPEN_ISSUE_LIMIT} --json number,title`\n" +
        "    )\n" +
        "  );",
    ],
    [
      "    gh(`issue list --state open --limit 200 --json number,title,labels`)",
      "    gh(\n" +
        "      `issue list --state open --limit ${OPEN_ISSUE_LIMIT} --json number,title,labels`\n" +
        "    )",
    ],
    [
      "const blockedByRowsSchema = z.array(\n" +
        "  z.object({ number: z.number(), blockedBy: z.array(z.number()) })\n" +
        ");\n" +
        "\n" +
        "function getBlockedByForInReview(): Map<number, number[]> {\n" +
        "  const out = gh(\n" +
        "    `issue list --state open --label \"in-review\" --limit 100 --json number,blockedBy --jq '[.[] | {number, blockedBy: [.blockedBy.nodes[].number]}]'`\n" +
        "  );\n" +
        "  const map = new Map<number, number[]>();\n" +
        "  if (!out) return map;\n" +
        "  for (const row of blockedByRowsSchema.parse(JSON.parse(out))) {\n" +
        "    map.set(row.number, row.blockedBy);\n" +
        "  }\n" +
        "  return map;",
      "function getBlockedByForInReview(): Map<number, number[]> {\n" +
        "  return parseBlockedByRows(\n" +
        "    gh(\n" +
        "      `issue list --state open --label \"in-review\" --limit ${OPEN_ISSUE_LIMIT} --json number,blockedBy --jq '[.[] | {number, blockedBy: [.blockedBy.nodes[].number]}]'`\n" +
        "    )\n" +
        "  );",
    ],
    [
      "const parentRowsSchema = z.array(\n" +
        "  z.object({ number: z.number(), parent: z.number().nullable() })\n" +
        ");\n" +
        "\n" +
        "function getParentEdges(): Map<string, string> {\n" +
        "  // ponytail: --limit 100 matches every other issue fetch here; a repo with\n" +
        "  // >100 open issues could miss a completed issue's parent edge (it then falls\n" +
        "  // back to the planner-declared parents). Raise the limit if that ceiling bites.\n" +
        "  const out = gh(\n" +
        "    `issue list --state open --limit 100 --json number,parent --jq '[.[] | {number, parent: .parent.number}]'`\n" +
        "  );\n" +
        "  const map = new Map<string, string>();\n" +
        "  if (!out) return map;\n" +
        "  for (const row of parentRowsSchema.parse(JSON.parse(out))) {\n" +
        "    if (row.parent !== null) map.set(String(row.number), String(row.parent));\n" +
        "  }\n" +
        "  return map;",
      "function getParentEdges(): Map<string, string> {\n" +
        "  // A repo with more open issues than OPEN_ISSUE_LIMIT could miss a completed\n" +
        "  // issue's parent edge; it then falls back to the planner-declared parents.\n" +
        "  return parseParentEdges(\n" +
        "    gh(\n" +
        "      `issue list --state open --limit ${OPEN_ISSUE_LIMIT} --json number,parent --jq '[.[] | {number, parent: .parent.number}]'`\n" +
        "    )\n" +
        "  );",
    ],
    [
      "const issueEdgeRowsSchema = z.array(\n" +
        "  z.object({\n" +
        "    number: z.number(),\n" +
        "    state: z.enum([\"OPEN\", \"CLOSED\"]),\n" +
        "    parent: z.number().nullable(),\n" +
        "  })\n" +
        ");\n" +
        "\n" +
        "// Every issue's id, state and parent \u2014 the one query behind both the closed-set\n" +
        "// `issueIsClosed` memoises (#127) and the spent-parent check below. Null when the\n" +
        "// query fails; each caller decides what that means for it.",
      "// The one query behind both the closed-set `issueIsClosed` memoises (#127) and\n" +
        "// the spent-parent check below. Null when there is no usable answer; each\n" +
        "// caller decides what that means for it.",
    ],
    [
      "// suggestion. Raise the limit if that ceiling bites.\n" +
        "function fetchIssueEdges(): z.infer<typeof issueEdgeRowsSchema> | null {\n" +
        "  const out = gh(\n" +
        "    `issue list --state all --limit 1000 --json number,state,parent --jq '[.[] | {number, state, parent: .parent.number}]'`\n" +
        "  );\n" +
        "  return out ? issueEdgeRowsSchema.parse(JSON.parse(out)) : null;",
      "// suggestion.\n" +
        "function fetchIssueEdges(): IssueEdgeRow[] | null {\n" +
        "  return parseIssueEdges(\n" +
        "    gh(\n" +
        "      `issue list --state all --limit ${ALL_ISSUE_LIMIT} --json number,state,parent --jq '[.[] | {number, state, parent: .parent.number}]'`\n" +
        "    )\n" +
        "  );",
    ],
  ],
  // .sandcastle/reconcile.mts and retry-policy.mts — the rest of #169. The
  // outcome kind is renamed and threaded with the axes that failed; the notes
  // and the counter key follow it. Declared hunk by hunk rather than re-pinning
  // PRE_ARC, because #119 has not rolled the arc out to the adopters yet and
  // re-pinning would retire the net that proves what the rollout carries.
  ".sandcastle/reconcile.mts": [
    [
      'import type { CheckVerdict } from "./review-verdict.mts";',
      'import type { CheckVerdict, ReviewAxis } from "./review-verdict.mts";',
    ],
    [
      "//   spec-fail    — reviewed, but the branch doesn't satisfy the issue.",
      "//   review-fail  — reviewed, but a review axis (spec and/or standards) failed;\n" +
        "//                  `failedAxes` names which. Re-implemented up to the cap.",
    ],
    [
      'export type OutcomeKind = "done" | "needs-review" | "spec-fail" | "nothing";',
      'export type OutcomeKind = "done" | "needs-review" | "review-fail" | "nothing";',
    ],
    [
      "  attempts: Attempts;\n" +
        "}): OutcomePlan {\n" +
        "  const { kind, issue, attempts } = input;",
      "  attempts: Attempts;\n" +
        "  // The review axes that failed, for a review-fail outcome — names the axis in\n" +
        '  // the operator note instead of always saying "spec". Absent otherwise.\n' +
        "  failedAxes?: ReviewAxis[];\n" +
        "}): OutcomePlan {\n" +
        "  const { kind, issue, attempts, failedAxes } = input;",
    ],
    [
      '  if (kind === "spec-fail") {\n' +
        '    // Re-review cannot repair "built the wrong thing" — only re-implementing\n' +
        "    // can. Counted under spec-<id> so a persistently-misunderstood issue burns\n" +
        "    // its own cap rather than the re-review one.\n" +
        "    const r = recordAttempt(attempts, `spec-${issue.id}`);",
      '  if (kind === "review-fail") {\n' +
        "    // Re-review cannot repair a failing review axis — only re-implementing can.\n" +
        "    // Both axes share one cap, counted under review-<id> so a persistently-\n" +
        "    // failing issue burns its own cap rather than the re-review one.\n" +
        '    const axes = failedAxes?.length ? failedAxes.join(", ") : "review";\n' +
        "    const r = recordAttempt(attempts, `review-${issue.id}`);",
    ],
    [
      "note: `${issue.id} failed spec review ${REVIEW_RETRY_CAP}x; handing to a human (ready-for-human)`,",
      "note: `${issue.id} failed review (${axes}) ${REVIEW_RETRY_CAP}x; handing to a human (ready-for-human)`,",
    ],
    [
      "note: `${issue.id} failed spec review; back to ready-for-agent to re-implement (attempt ${r.count}/${REVIEW_RETRY_CAP})`,",
      "note: `${issue.id} failed review (${axes}); back to ready-for-agent to re-implement (attempt ${r.count}/${REVIEW_RETRY_CAP})`,",
    ],
    // #104 — the PR states become values so github-parse.mts can build its zod
    // schema from them instead of hand-copying the union.
    [
      'export type PrState = "OPEN" | "CLOSED" | "MERGED";',
      "// Exported as values, not just as a union, because github-parse.mts builds the\n" +
        "// zod schema that admits a PR state from this array. Written out twice instead,\n" +
        "// the schema would reject a state this type accepts and nothing would say so.\n" +
        'export const PR_STATES = ["OPEN", "CLOSED", "MERGED"] as const;\n' +
        "export type PrState = (typeof PR_STATES)[number];",
    ],
  ],
  ".sandcastle/retry-policy.mts": [
    [
      "// escalate to a full re-implement. A spec-fail issue is re-implemented up to\n" +
        "// this many times before being handed to a human. Without a cap, a\n" +
        "// deterministically-broken branch would re-review/re-fail every run forever.",
      "// escalate to a full re-implement. A review-fail issue (spec and/or standards)\n" +
        "// is re-implemented up to this many times before being handed to a human.\n" +
        "// Without a cap, a deterministically-broken branch would re-review/re-fail\n" +
        "// every run forever.",
    ],
    [
      "// (review-retry) or `spec-<id>` (spec re-implement), kept distinct so the two\n" +
        "// caps count independently for the same issue.",
      "// (review-retry) or `review-<id>` (re-implement after a failed review axis),\n" +
        "// kept distinct so the two caps count independently for the same issue.",
    ],
    // #103: the Phase-3 gate's set-level fold arrives here from main.mts, and
    // takes the verdict status by its own type rather than restating the union.
    // #105 adds the zod import beside it — the attempts file is now validated.
    [
      'import { readFileSync, writeFileSync } from "node:fs";',
      'import { readFileSync, writeFileSync } from "node:fs";\n' +
        "\n" +
        'import { z } from "zod";\n' +
        "\n" +
        'import type { CheckStatus } from "./review-verdict.mts";',
    ],
    [
      "  next[key] = count;\n" +
        "  return { attempts: next, count, escalate: false };\n" +
        "}",
      "  next[key] = count;\n" +
        "  return { attempts: next, count, escalate: false };\n" +
        "}\n" +
        "\n" +
        "// One gate verdict against a whole PR set: the Phase-3 full-suite gate judges\n" +
        "// every member at once, under one counter per member (#25). A `test-fail`\n" +
        "// counts one attempt against each key; a `pass` clears them, which is what makes\n" +
        "// the cap count CONSECUTIVE failures; a `harness-error` is an infra fault and is\n" +
        "// never counted, so a sandbox that failed to launch cannot retire a good set.\n" +
        "//\n" +
        "// `escalated` is an OR across every key, never last-one-wins. The set fails and\n" +
        "// passes in lockstep, so its counters normally move together — but recordAttempt\n" +
        "// deletes a key as it escalates, so counters that ever drifted apart would let a\n" +
        "// last-wins read miss the escalation and requeue the set forever. Pure: the\n" +
        "// input map is not mutated.\n" +
        "export function recordSetAttempt(\n" +
        "  attempts: Attempts,\n" +
        "  keys: string[],\n" +
        "  status: CheckStatus\n" +
        "): { attempts: Attempts; escalated: boolean } {\n" +
        "  let next = { ...attempts };\n" +
        '  if (status === "pass") {\n' +
        "    for (const key of keys) delete next[key];\n" +
        "    return { attempts: next, escalated: false };\n" +
        "  }\n" +
        '  if (status !== "test-fail") return { attempts: next, escalated: false };\n' +
        "  let escalated = false;\n" +
        "  for (const key of keys) {\n" +
        "    const r = recordAttempt(next, key);\n" +
        "    next = r.attempts;\n" +
        "    escalated ||= r.escalate;\n" +
        "  }\n" +
        "  return { attempts: next, escalated };\n" +
        "}",
    ],
    // #105: the attempts type is now derived from a zod schema, and readAttempts
    // validates the parsed file instead of casting it.
    [
      "export type Attempts = Record<string, number>;\n" +
        "\n" +
        "export function readAttempts(file = ATTEMPTS_FILE): Attempts {\n" +
        "  try {\n" +
        '    return JSON.parse(readFileSync(file, "utf8"));\n' +
        "  } catch {\n" +
        "    return {};\n" +
        "  }\n" +
        "}",
      "// A value is a tally of failed attempts, so a whole number that never dips\n" +
        "// below zero. A negative or fractional count is corruption, and the schema\n" +
        "// treats it as such rather than letting it steer a cap.\n" +
        "const attemptsSchema = z.record(z.string(), z.number().int().nonnegative());\n" +
        "export type Attempts = z.infer<typeof attemptsSchema>;\n" +
        "\n" +
        "// The file is state this tool wrote last run, but a run can be killed mid-write\n" +
        "// and a human can edit it, so it is outside data like any other (CODING_STANDARDS\n" +
        "// rule 2 names this very file). A missing, unparseable, or mis-typed file all\n" +
        "// read as empty: the caps then start fresh, which at worst grants a few extra\n" +
        "// retries — the safe direction. Reading a bad count as a real one is the outcome\n" +
        "// the schema exists to forbid, so a partially-valid file is rejected whole rather\n" +
        "// than trusted in part.\n" +
        "export function readAttempts(file = ATTEMPTS_FILE): Attempts {\n" +
        "  let json: unknown;\n" +
        "  try {\n" +
        '    json = JSON.parse(readFileSync(file, "utf8"));\n' +
        "  } catch {\n" +
        "    return {}; // missing file (first run) or non-JSON contents\n" +
        "  }\n" +
        "  const parsed = attemptsSchema.safeParse(json);\n" +
        "  return parsed.success ? parsed.data : {};\n" +
        "}",
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
  // .sandcastle/CODING_STANDARDS.md, .sandcastle/log-retention.mts,
  // .sandcastle/main.mts — the ADRs stopped shipping (#182), so the citations
  // pointing at them went with the files. Each rule and reason already stood on
  // its own line; only the unfollowable pointer goes.
  ".sandcastle/CODING_STANDARDS.md": [
    [
      "1. **`main.mts` is the entrypoint, not a module \u2014 never import from it** (ADR-0002).",
      "1. **`main.mts` is the entrypoint, not a module \u2014 never import from it.**",
    ],
  ],
  ".sandcastle/log-retention.mts": [
    [
      "// Pure log-retention decision, split out of main.mts per ADR-0002 so it can be",
      "// Pure log-retention decision, split out of main.mts so it can be",
    ],
  ],
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
};

// Files deliberately REWRITTEN end to end since the pin, where a from→to pair
// per hunk would put a copy of the whole new file in this test — a ledger that
// says only "the file equals this copy of the file", and that has to be
// rewritten again on the next edit. Listing one drops the body from the byte
// net; its presence stays pinned by the set net above, and its behaviour by its
// own unit tests.
//   .sandcastle/github-parse.mts — #104 made this the single home for `gh` JSON
//   parsing: three parsers moved in from main.mts, the trust-casts became zod
//   schemas, and one failure policy replaced two. Roughly 20 lines of the
//   original survive. github-parse.test.mjs covers every parser, malformed
//   input included.
// Reach for a pair in ARC_REWRITTEN_PROSE first — this list is for a file the
// ticket genuinely replaced, not a file it edited a lot.
const ARC_REWRITTEN_RENDERS = [".sandcastle/github-parse.mts"];

// Answers each arc ticket deliberately ADDS to a Python adopter's breadcrumb.
// The net below demands the breadcrumb equal the pre-arc one plus exactly these,
// so a ticket declares its addition instead of the assertion quietly widening.
const ARC_ADDED_ANSWERS = ["LANGUAGE: python"];

// Files the template deliberately ADDS since the pin. Same bargain as the
// answers list: the set-equality net stays exact, and a new render is declared
// rather than the assertion quietly widening to "a superset is fine".
//   (none — ADR 0004 arrived with #127 and left again with #182, below)
const ARC_ADDED_RENDERS = [];

// The mirror: files the template deliberately WITHDRAWS since the pin. Without
// it a withdrawal has only one way past the net — widening set-equality to "a
// subset is fine" — which retires the net for every later ticket. Declared here,
// the assertion stays exact in both directions.
//   CONTEXT.md, docs/adr/*  — the project's own domain model, maintainer reading
//   sandbox-identity.check.mts — a developer's self-check, now in the dev suite
// All three keep their home in this repo; only what an adopter receives changed.
const ARC_WITHDRAWN_RENDERS = [
  ".sandcastle/CONTEXT.md",
  ".sandcastle/docs/adr/0001-dependency-forest-with-topic-grouped-prs.md",
  ".sandcastle/docs/adr/0002-main-is-an-unimported-script.md",
  ".sandcastle/docs/adr/0003-multi-parent-conflict-abort-not-resolve.md",
  ".sandcastle/sandbox-identity.check.mts",
];

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
    expect([...renderedTree(after).keys()].sort()).toEqual(
      [
        ...[...renderedTree(before).keys()].filter((p) => !ARC_WITHDRAWN_RENDERS.includes(p)),
        ...ARC_ADDED_RENDERS,
      ].sort()
    );
  });

  test("renders every file byte-identically to the pre-arc template", () => {
    const [was, is] = [renderedTree(before), renderedTree(after)];
    for (const [path, body] of was) {
      if (path === BREADCRUMB) continue;
      // A withdrawn file has no counterpart to compare; the set test above owns it.
      if (ARC_WITHDRAWN_RENDERS.includes(path)) continue;
      // A file the ticket replaced outright — its own unit tests own it now.
      if (ARC_REWRITTEN_RENDERS.includes(path)) continue;
      // Rewrites first, then the append check reads what they left: a file can
      // be edited in place AND appended to, and taking the append shortcut first
      // would excuse every edit above the appended text in such a file.
      let expected = body;
      for (const [from, to] of ARC_REWRITTEN_PROSE[path] ?? []) {
        expect(expected, `${path}: declared rewrite no longer matches the pre-arc text`).toContain(
          from
        );
        expected = expected.replace(from, to);
      }
      if (ARC_APPENDED_RENDERS.includes(path)) {
        expect(
          is.get(path)?.startsWith(expected),
          `${path} changed above the appended text`
        ).toBe(true);
        continue;
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
  // A bump has to move the RENDER, not just the commit: CONTEXT.md no longer
  // ships (#182), so appending there would leave every version identical to an
  // adopter and the update under test with nothing to carry.
  const bump = (gsrc, tag) => {
    appendFileSync(
      join(src, "setup-sandcastle", "templates", ".sandcastle", "CODING_STANDARDS.md"),
      "\n"
    );
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

  // Withdrawing a file from the render is an `_exclude` rule, and a rule that
  // matched one arm's path and not the other's would leave two fleets carrying
  // different files. The twin is the python arm of the same template.
  test("renders the same set of files as the python arm", () => {
    expect([...renderedTree(fresh).keys()].sort()).toEqual([...renderedTree(twin).keys()].sort());
  });

  test("records LANGUAGE as node in the breadcrumb", () => {
    expect(answersIn(fresh)).toMatch(recordedAnswer("LANGUAGE", "node"));
  });

  test("gets the sandcastle:local marker rule too — it is not a python-arm rule", () => {
    expectTheLocalMarkerRule(standardsIn(fresh));
  });

  test("gets the formatting rule too — it is not a python-arm rule", () => {
    expectTheFormattingRule(standardsIn(fresh));
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

  // review-verdict.mts is NOT a template: its two Python-naming comments talk
  // about the gate wrapper, whose command check-prompt.md already renders, so
  // they point at it instead of repeating it. Templating a module that 222
  // lines of dev tests import by name, for comment prose, was the worse trade.
  // Both arms therefore get the same file, and this is what says so — if a
  // later ticket does branch it, this fails and the choice gets made again.
  test("renders one review-verdict.mts for both arms, naming no recipe", () => {
    const gate = renderedIn(fresh, "review-verdict.mts");
    expect(gate).toBe(renderedIn(twin, "review-verdict.mts"));
    expect(gate).not.toMatch(/just (check|lint|typecheck)/);
    // The sentinel is a host-coupled contract string (CODING_STANDARDS rule 3):
    // the prose around it moved, the string itself must not.
    expect(gate).toContain("SANDCASTLE_CHECK:");
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
  // The vehicle is a file the render actually carries: CONTEXT.md was withdrawn
  // (#182), and a merge into a file no adopter receives proves nothing.
  const docInSrc = () =>
    join(src, "setup-sandcastle", "templates", ".sandcastle", "CODING_STANDARDS.md");
  const docInTarget = () => join(target, ".sandcastle", "CODING_STANDARDS.md");

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
    appendFileSync(docInTarget(), `\n${ADOPTER}\n`);
    gtgt("add", "-A");
    gtgt("commit", "-q", "-m", "adopter edit");

    // --- template evolves to v2 ---
    appendFileSync(docInSrc(), `\n${TEMPLATE_V2}\n`);
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
    expect(readFileSync(docInTarget(), "utf8")).toContain(ADOPTER);
  });

  test("3-way merge lands the new template version's change", () => {
    expect(readFileSync(docInTarget(), "utf8")).toContain(TEMPLATE_V2);
  });
});
