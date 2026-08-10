import { test, expect, describe, beforeAll, afterAll } from "vitest";
import { execFileSync, spawnSync } from "node:child_process";
import {
  appendFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// `sandcastle-propagate` is driven end to end, as the sweep runs it: a fixture
// template repo (SKILLS_REPO), a fixture tree of adopters (SEARCH_ROOT), and a
// bare remote for each so the script's commit+push completes. We observe the
// script's stdout banner, each adopter's git state, and the arguments it hands
// a recording `gh` — never its internals.
const here = dirname(fileURLToPath(import.meta.url));
// tests/ -> .sandcastle/ -> templates/ -> setup-sandcastle/ -> repo root
const repoRoot = join(here, "..", "..", "..", "..");
const SCRIPT = join(repoRoot, "setup-sandcastle", "sandcastle-propagate");
const BREADCRUMB = ".copier-answers.yml";

const gitIn = (dir) => (...args) => execFileSync("git", ["-C", dir, ...args], { encoding: "utf8" });

const initRepo = (dir) => {
  const g = gitIn(dir);
  g("init", "-q", "-b", "main");
  g("config", "user.email", "test@example.com");
  g("config", "user.name", "Test");
  return g;
};

const answersIn = (dir) => readFileSync(join(dir, BREADCRUMB), "utf8");

const recordedAnswer = (name, value) => new RegExp(`^${name}: ['"]?${value.replaceAll(".", "\\.")}['"]?$`, "m");

function hasCopier() {
  try {
    execFileSync("copier", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

// A throwaway template repo holding the LIVE template at one tag. The script
// only sweeps a breadcrumb whose `_src_path` names our template, and copier
// records that path verbatim — so the source has to LIVE at a caneff/agent-skills
// path. `bump` moves it on a tag at a time, giving a sweep something to carry.
function fixtureTemplate(tag) {
  const root = mkdtempSync(join(tmpdir(), "sandcastle-prop-src-"));
  const src = join(root, "caneff", "agent-skills");
  mkdirSync(src, { recursive: true });
  cpSync(join(repoRoot, "copier.yml"), join(src, "copier.yml"));
  cpSync(join(repoRoot, "setup-sandcastle", "templates"), join(src, "setup-sandcastle", "templates"), {
    recursive: true,
  });
  const g = initRepo(src);
  g("add", "-A");
  g("commit", "-q", "-m", tag);
  g("tag", tag);
  return {
    root,
    src,
    bump(next) {
      appendFileSync(join(src, "setup-sandcastle", "templates", ".sandcastle", "CONTEXT.md"), "\n");
      g("commit", "-q", "-am", next);
      g("tag", next);
    },
  };
}

const PR_URL = "https://github.test/acme/repo/pull/7";

// A recording `gh`. Every invocation appends its arguments to one log, NUL
// separated and led by a marker, so a PR body full of newlines still parses
// back into one call per entry. The canned answers stand in for GitHub: `auth`
// succeeds unless `auth` says otherwise, `pr list` prints `openPr` (empty for
// an adopter with no sweep PR waiting), `pr create` prints a URL.
function ghShim(dir, { openPr = "", auth = 0, prUrl = PR_URL } = {}) {
  const bin = join(dir, "bin");
  mkdirSync(bin, { recursive: true });
  const log = join(dir, "gh.log");
  const q = JSON.stringify;
  writeFileSync(
    join(bin, "gh"),
    [
      "#!/bin/sh",
      `printf '%s\\0' "@@" "$@" >> ${q(log)}`,
      `[ "$1" = auth ] && exit ${auth}`,
      `[ "$1$2" = prlist ] && { printf '%s' ${q(openPr)}; exit 0; }`,
      `[ "$1$2" = prcreate ] && { printf '%s\\n' ${q(prUrl)}; exit 0; }`,
      "exit 0",
    ].join("\n") + "\n",
    { mode: 0o755 }
  );
  // One entry per invocation, each an array of that call's arguments.
  const calls = () =>
    existsSync(log)
      ? readFileSync(log, "utf8").split("@@\0").slice(1).map((c) => c.split("\0").slice(0, -1))
      : [];
  return { dir, bin, calls, callsTo: (...verb) => calls().filter((c) => verb.every((v, i) => c[i] === v)) };
}

// An adopter that installed the template at `ref`, with a bare remote so the
// sweep's commit+push completes.
function fixtureAdopter(searchRoot, name, src, ref, data) {
  const repo = join(searchRoot, name);
  const remote = join(searchRoot, ".remotes", `${name}.git`);
  mkdirSync(repo);
  const g = initRepo(repo);
  writeFileSync(join(repo, "README.md"), `# ${name}\n`);
  g("add", "-A");
  g("commit", "-q", "-m", "init adopter");
  execFileSync(
    "copier",
    ["copy", "--defaults", "--vcs-ref", ref, ...(data ? ["--data", data] : []), src, repo],
    { encoding: "utf8" }
  );
  return { repo, remote, g, publish: () => {
    g("add", "-A");
    g("commit", "-q", "-m", "install sandcastle");
    // The remote lives under the fixture root so it is discarded with it. Bare,
    // so it carries no breadcrumb and the sweep's `find` walks past it.
    execFileSync("git", ["init", "-q", "--bare", "-b", "main", remote]);
    g("remote", "add", "origin", remote);
    g("push", "-q", "-u", "origin", "main");
  } };
}

// The branch the sweep pushes, for a given target ref.
const branchFor = (ref) => `sandcastle/update-to-${ref.replaceAll(/[^A-Za-z0-9._-]/g, "-")}`;

// What the sweep proposed, read off the pushed branch — the local checkout is
// restored, so the adopter's own working tree can no longer answer this.
const answersOn = (remote, ref) =>
  execFileSync("git", ["-C", remote, "show", `${branchFor(ref)}:${BREADCRUMB}`], { encoding: "utf8" });

// `bin` goes in front of `PATH` so the recording `gh` wins; `path` replaces
// `PATH` outright, for the run that has to find no `gh` at all.
const propagate = (src, searchRoot, args = [], { bin, path } = {}) =>
  spawnSync("bash", [SCRIPT, ...args], {
    encoding: "utf8",
    env: {
      ...process.env,
      SKILLS_REPO: src,
      SEARCH_ROOT: searchRoot,
      PATH: path ?? (bin ? `${bin}:${process.env.PATH}` : process.env.PATH),
    },
  });

describe.skipIf(!hasCopier())("sandcastle-propagate sweeps the adopters it finds", () => {
  let template;
  let searchRoot;
  let sweep;
  let gh;
  let adopters;
  let before;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";
  const stateOf = (dir) => ({
    head: gitIn(dir)("rev-parse", "HEAD"),
    branch: gitIn(dir)("rev-parse", "--abbrev-ref", "HEAD"),
    status: gitIn(dir)("status", "--porcelain"),
  });

  beforeAll(() => {
    template = fixtureTemplate(V1);
    // Two adopters side by side, each installed at v1: one python (its version
    // must survive), one node (never asked for one).
    searchRoot = mkdtempSync(join(tmpdir(), "sandcastle-prop-adopters-"));

    const py = fixtureAdopter(searchRoot, "py-adopter", template.src, V1, "PYTHON_VERSION=3.14");
    // A file the template never rendered, so the sweep's own report has
    // something to find. Added rather than edited: an edit to a file the
    // template also moves would land as a merge conflict, not divergence.
    writeFileSync(join(py.repo, ".sandcastle", "local-only.mts"), "export const x = 1;\n");
    py.publish();

    const node = fixtureAdopter(searchRoot, "node-adopter", template.src, V1, "LANGUAGE=node");
    // The live node adopter reached today's template through the one-time
    // LANGUAGE correction and still carries the empty answer that correction
    // left behind. Start from that state, not from a clean node install, so
    // the sweep has a stale key to leave alone.
    appendFileSync(join(node.repo, BREADCRUMB), "PYTHON_VERSION: ''\n");
    node.publish();

    // The template moves on, so there is something for the sweep to carry.
    template.bump(V2);
    adopters = { "py-adopter": py, "node-adopter": node };
    before = Object.fromEntries(
      Object.entries(adopters).map(([name, a]) => [
        name,
        { local: stateOf(a.repo), main: gitIn(a.remote)("rev-parse", "main") },
      ])
    );
    gh = ghShim(mkdtempSync(join(tmpdir(), "sandcastle-prop-gh-")));
    sweep = propagate(template.src, searchRoot, [], { bin: gh.bin });
  });
  afterAll(() =>
    [template?.root, searchRoot, gh?.dir].forEach((d) => d && rmSync(d, { recursive: true, force: true }))
  );

  test("sweeps both adopters to the newest template tag", () => {
    expect(sweep.status, sweep.stderr).toBe(0);
    expect(sweep.stdout).toContain(`Propagating ${V2}`);
    expect(sweep.stdout).toContain("updated=2 skipped=0");
  });

  test("announces each repo by the ecosystem it recorded, not its Python version", () => {
    expect(sweep.stdout).toContain("== py-adopter (LANGUAGE=python) ==");
    expect(sweep.stdout).toContain("== node-adopter (LANGUAGE=node) ==");
  });

  test("leaves a python adopter's recorded version untouched", () => {
    expect(answersOn(adopters["py-adopter"].remote, V2)).toMatch(recordedAnswer("PYTHON_VERSION", "3.14"));
  });

  // The sweep carries the template and then says what it could not carry — the
  // same report `--divergence` prints alone, per repo, after each update.
  test("prints each repo's divergence report after updating it", () => {
    expect(sweep.stdout).toMatch(/py-adopter\s+\.sandcastle\/local-only\.mts\s+NEW\s+UNMARKED/);
  });

  // The harm the re-assert did: on a node adopter the lookup came back empty and
  // the script fed an answer back in that the template no longer asks for.
  test("never puts a Python version into a node adopter's breadcrumb", () => {
    expect(answersOn(adopters["node-adopter"].remote, V2)).not.toMatch(/PYTHON_VERSION/);
  });

  // The update goes up as a proposal. Every adopter runs PR CI, so a review and
  // a check both see the change before it can reach a default branch.
  test("pushes the update to a branch named for the ref, never to main", () => {
    for (const [name, a] of Object.entries(adopters)) {
      const g = gitIn(a.remote);
      expect(() => g("rev-parse", `refs/heads/${branchFor(V2)}`), name).not.toThrow();
      expect(g("rev-parse", "main"), name).toBe(before[name].main);
    }
  });

  test("leaves each adopter's checked-out branch exactly where it found it", () => {
    for (const [name, a] of Object.entries(adopters)) {
      expect(stateOf(a.repo), name).toEqual(before[name].local);
    }
  });

  test("checks gh auth once, before it touches a repo", () => {
    expect(gh.callsTo("auth")).toHaveLength(1);
    expect(gh.calls()[0]).toEqual(["auth", "status"]);
  });

  test("opens one PR per adopter and prints its URL", () => {
    expect(gh.callsTo("pr", "create")).toHaveLength(2);
    expect(sweep.stdout).toContain(PR_URL);
    const create = gh.callsTo("pr", "create")[0];
    expect(create).toContain("--head");
    expect(create[create.indexOf("--head") + 1]).toBe(branchFor(V2));
  });

  // The body is the divergence report under the two refs, so a reviewer reads
  // what moved and what the merge could not carry in the same place.
  test("gives the PR the update title and a body carrying both refs and the report", () => {
    const create = gh.callsTo("pr", "create").find((c) => c.some((a) => a.includes("local-only.mts")));
    expect(create[create.indexOf("--title") + 1]).toBe(`chore(sandcastle): update template to ${V2}`);
    const body = create[create.indexOf("--body") + 1];
    expect(body).toContain(V1);
    expect(body).toContain(V2);
    expect(body).toMatch(/\.sandcastle\/local-only\.mts\s+NEW\s+UNMARKED/);
  });
});

// Four sweeps that must land nothing, run in turn against one adopter. Each
// leaves the repo as it found it, so they compose: the state asserted at the
// end is the state every one of them was handed.
describe.skipIf(!hasCopier())("sandcastle-propagate refuses to sweep", () => {
  let template;
  let searchRoot;
  let adopter;
  let before;
  let runs;
  let shims;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";
  const shimDir = () => mkdtempSync(join(tmpdir(), "sandcastle-refuse-gh-"));
  // A `PATH` holding one entry: `bash`, so the script can start, and nothing
  // else — so `gh` is genuinely absent however the machine has it installed.
  const bashOnly = () => {
    const dir = join(shimDir(), "bash-only");
    mkdirSync(dir, { recursive: true });
    symlinkSync(execFileSync("bash", ["-c", "command -v bash"], { encoding: "utf8" }).trim(), join(dir, "bash"));
    return dir;
  };

  beforeAll(() => {
    template = fixtureTemplate(V1);
    searchRoot = mkdtempSync(join(tmpdir(), "sandcastle-refuse-adopters-"));
    adopter = fixtureAdopter(searchRoot, "py-adopter", template.src, V1, "PYTHON_VERSION=3.14");
    adopter.publish();
    template.bump(V2);
    before = {
      head: gitIn(adopter.repo)("rev-parse", "HEAD"),
      status: gitIn(adopter.repo)("status", "--porcelain"),
      branches: gitIn(adopter.remote)("branch", "--list"),
    };

    shims = { unauth: ghShim(shimDir(), { auth: 1 }), dry: ghShim(shimDir()), busy: ghShim(shimDir(), { openPr: PR_URL }) };
    runs = {
      // No `gh` at all. The ref is passed, so the run needs nothing off `PATH`
      // before the check it must die on.
      noGh: propagate(template.src, searchRoot, [V2], { path: bashOnly() }),
      unauth: propagate(template.src, searchRoot, [], { bin: shims.unauth.bin }),
      dry: propagate(template.src, searchRoot, ["--dry-run"], { bin: shims.dry.bin }),
      busy: propagate(template.src, searchRoot, [], { bin: shims.busy.bin }),
    };
  });
  afterAll(() =>
    [template?.root, searchRoot, ...Object.values(shims ?? {}).map((s) => s.dir)].forEach(
      (d) => d && rmSync(d, { recursive: true, force: true })
    )
  );

  test("aborts when gh is missing, before it reaches the first repo", () => {
    expect(runs.noGh.status).toBe(1);
    expect(runs.noGh.stderr).toMatch(/gh/);
    expect(runs.noGh.stdout).not.toContain("== py-adopter");
  });

  test("aborts when gh is not authenticated, before it reaches the first repo", () => {
    expect(runs.unauth.status).toBe(1);
    expect(runs.unauth.stderr).toMatch(/authenticated/);
    expect(runs.unauth.stdout).not.toContain("== py-adopter");
  });

  // The flag exists to be run before authenticating, so it must stop short of
  // `gh` entirely — not merely stop short of opening anything.
  test("--dry-run completes without calling gh at all", () => {
    expect(runs.dry.status, runs.dry.stderr).toBe(0);
    expect(runs.dry.stdout).toContain("== py-adopter");
    expect(shims.dry.calls()).toEqual([]);
  });

  test("skips an adopter whose sweep PR is still open, naming it", () => {
    expect(runs.busy.status, runs.busy.stderr).toBe(0);
    expect(runs.busy.stdout).toContain(PR_URL);
    expect(runs.busy.stdout).toContain("updated=0 skipped=1");
    expect(shims.busy.callsTo("pr", "create")).toEqual([]);
  });

  test("leaves the adopter and its remote untouched throughout", () => {
    expect(gitIn(adopter.repo)("rev-parse", "HEAD")).toBe(before.head);
    expect(gitIn(adopter.repo)("status", "--porcelain")).toBe(before.status);
    expect(gitIn(adopter.remote)("branch", "--list")).toBe(before.branches);
    expect(answersIn(adopter.repo)).toContain(V1);
  });
});

// The divergence report. The fixture holds every shape the report has to tell
// apart: a marked hunk, an unmarked hunk, an adopter-added file, and — in a
// second repo — the change that is NOT divergence, simply lagging a tag behind.
const REASON = "the agent cache needs a Chromium binary";

describe.skipIf(!hasCopier())("sandcastle-propagate --divergence", () => {
  let template;
  let searchRoot;
  let report;
  let before;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";
  const lines = (name) => report.stdout.split("\n").filter((l) => l.startsWith(name));
  const lineFor = (file) => lines("diverged").find((l) => l.includes(file));

  beforeAll(() => {
    template = fixtureTemplate(V1);
    searchRoot = mkdtempSync(join(tmpdir(), "sandcastle-div-adopters-"));

    const diverged = fixtureAdopter(searchRoot, "diverged", template.src, V1, "PYTHON_VERSION=3.14");
    const sand = (f) => join(diverged.repo, ".sandcastle", f);
    // Marked: a comment in the file's own syntax carrying the token and a reason.
    appendFileSync(sand("Dockerfile"), `\n# sandcastle:local — ${REASON}\nRUN echo local\n`);
    // Unmarked: an edit to a rendered file with nothing said about it. The
    // `++ `/`-- ` lines are the trap: prefixed with the diff's own `+`, they
    // arrive looking exactly like the `+++ `/`--- ` file headers the report
    // parses, and prose under `.sandcastle/` really does quote diffs.
    appendFileSync(sand("CONTEXT.md"), "\nA local paragraph nobody marked.\n++ not a header\n-- nor this\n");
    // Adopter-added: no counterpart in the render at all.
    writeFileSync(sand("extra.mts"), "export const local = 1;\n");
    diverged.publish();

    // Untouched, and deliberately left behind the newest tag.
    fixtureAdopter(searchRoot, "lagging", template.src, V1, "PYTHON_VERSION=3.14").publish();

    template.bump(V2);
    before = {
      head: gitIn(join(searchRoot, "diverged"))("rev-parse", "HEAD"),
      status: gitIn(join(searchRoot, "diverged"))("status", "--porcelain"),
    };
    report = propagate(template.src, searchRoot, ["--divergence"]);
  });
  afterAll(() => [template?.root, searchRoot].forEach((d) => d && rmSync(d, { recursive: true, force: true })));

  test("exits 0 — the report reports, it never blocks", () => {
    expect(report.status, report.stderr).toBe(0);
  });

  test("leaves the adopter's git state exactly as it found it", () => {
    const g = gitIn(join(searchRoot, "diverged"));
    expect(g("rev-parse", "HEAD")).toBe(before.head);
    expect(g("status", "--porcelain")).toBe(before.status);
    // Nothing was carried either: the recorded ref is still the tag it installed.
    expect(answersIn(join(searchRoot, "diverged"))).toContain(V1);
  });

  test("reports a marked hunk with its file, line, size and reason", () => {
    expect(lineFor("Dockerfile")).toMatch(/\.sandcastle\/Dockerfile:\d+\s+\+\d+ -\d+\s+local: /);
    expect(lineFor("Dockerfile")).toContain(REASON);
  });

  test("reports an unmarked hunk with its file, line and size", () => {
    expect(lineFor("CONTEXT.md")).toMatch(/\.sandcastle\/CONTEXT\.md:\d+\s+\+\d+ -\d+\s+UNMARKED$/);
  });

  test("reports an adopter-added file as its own NEW line", () => {
    expect(lineFor("extra.mts")).toMatch(/\.sandcastle\/extra\.mts\s+NEW\s+UNMARKED$/);
  });

  test("lists unmarked hunks before marked ones", () => {
    const verdicts = lines("diverged").map((l) => (l.includes("local: ") ? "marked" : "unmarked"));
    expect(verdicts).toEqual([...verdicts].sort().reverse());
    expect(new Set(verdicts)).toEqual(new Set(["unmarked", "marked"]));
  });

  // Diffing against the newest tag instead of the recorded `_commit` would make
  // this repo indistinguishable from one that had actually diverged.
  test("says nothing about an adopter that has only fallen behind the newest tag", () => {
    expect(lines("lagging")).toEqual([]);
  });
});
