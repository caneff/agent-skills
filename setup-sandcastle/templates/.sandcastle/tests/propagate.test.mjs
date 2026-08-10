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

// The branch the sweep pushes for `sandcastle-template/v2`, spelled out: the
// contract is this name, not whatever the script's sanitizer happens to emit.
const V2_BRANCH = "sandcastle/update-to-sandcastle-template-v2";

// What the sweep proposed, read off the pushed branch — the local checkout is
// restored, so the adopter's own working tree can no longer answer this.
const answersOn = (remote, branch) =>
  execFileSync("git", ["-C", remote, "show", `${branch}:${BREADCRUMB}`], { encoding: "utf8" });

// One adopter's git state, for asserting the sweep handed it back unchanged.
const stateOf = (dir) => ({
  head: gitIn(dir)("rev-parse", "HEAD"),
  branch: gitIn(dir)("rev-parse", "--abbrev-ref", "HEAD"),
  status: gitIn(dir)("status", "--porcelain"),
});

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
    expect(sweep.stdout).toContain("Done. updated=2 current=0 skipped=0 failed=0");
  });

  test("announces each repo by the ecosystem it recorded, not its Python version", () => {
    expect(sweep.stdout).toContain("== py-adopter (LANGUAGE=python) ==");
    expect(sweep.stdout).toContain("== node-adopter (LANGUAGE=node) ==");
  });

  test("leaves a python adopter's recorded version untouched", () => {
    expect(answersOn(adopters["py-adopter"].remote, V2_BRANCH)).toMatch(recordedAnswer("PYTHON_VERSION", "3.14"));
  });

  // The sweep carries the template and then says what it could not carry — the
  // same report `--divergence` prints alone, per repo, after each update.
  test("prints each repo's divergence report after updating it", () => {
    expect(sweep.stdout).toMatch(/py-adopter\s+\.sandcastle\/local-only\.mts\s+NEW\s+UNMARKED/);
  });

  // The harm the re-assert did: on a node adopter the lookup came back empty and
  // the script fed an answer back in that the template no longer asks for.
  test("never puts a Python version into a node adopter's breadcrumb", () => {
    expect(answersOn(adopters["node-adopter"].remote, V2_BRANCH)).not.toMatch(/PYTHON_VERSION/);
  });

  // The update goes up as a proposal. Every adopter runs PR CI, so a review and
  // a check both see the change before it can reach a default branch.
  test("pushes the update to a branch named for the ref, never to main", () => {
    for (const [name, a] of Object.entries(adopters)) {
      const g = gitIn(a.remote);
      expect(() => g("rev-parse", `refs/heads/${V2_BRANCH}`), name).not.toThrow();
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
    expect(create[create.indexOf("--head") + 1]).toBe(V2_BRANCH);
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

// The two paths where the push itself is the problem, swept together: one
// adopter whose sweep branch is already on the remote pointing somewhere else,
// and one whose remote is gone.
describe.skipIf(!hasCopier())("sandcastle-propagate pushes onto an obstructed remote", () => {
  let template;
  let searchRoot;
  let sweep;
  let gh;
  let stale;
  let broken;
  let before;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";

  beforeAll(() => {
    template = fixtureTemplate(V1);
    searchRoot = mkdtempSync(join(tmpdir(), "sandcastle-push-adopters-"));

    // A sweep branch left behind by an earlier run — its PR merged or closed, so
    // the open-PR skip does not catch it — sitting on an unrelated commit. A
    // plain push of the new update is a non-fast-forward reject.
    stale = fixtureAdopter(searchRoot, "stale-branch", template.src, V1, "PYTHON_VERSION=3.14");
    stale.publish();
    writeFileSync(join(stale.repo, "stale.txt"), "an earlier sweep\n");
    stale.g("add", "-A");
    stale.g("commit", "-q", "-m", "an earlier sweep");
    stale.g("push", "-q", "origin", `HEAD:refs/heads/${V2_BRANCH}`);
    stale.g("reset", "-q", "--hard", "HEAD~1");

    // Nowhere to push at all.
    broken = fixtureAdopter(searchRoot, "broken-remote", template.src, V1, "PYTHON_VERSION=3.14");
    broken.publish();
    broken.g("remote", "set-url", "origin", join(searchRoot, ".remotes", "gone.git"));

    template.bump(V2);
    before = { stale: stateOf(stale.repo), broken: stateOf(broken.repo) };
    gh = ghShim(mkdtempSync(join(tmpdir(), "sandcastle-push-gh-")));
    sweep = propagate(template.src, searchRoot, [], { bin: gh.bin });
  });
  afterAll(() =>
    [template?.root, searchRoot, gh?.dir].forEach((d) => d && rmSync(d, { recursive: true, force: true }))
  );

  test("carries the update onto a sweep branch an earlier run left behind", () => {
    expect(answersOn(stale.remote, V2_BRANCH)).toContain(V2);
    expect(gitIn(stale.remote)("rev-parse", V2_BRANCH)).not.toBe(before.stale.head);
  });

  // The load-bearing property of the whole change: the restore runs on the
  // failure path too, so a repo the sweep could not push is a repo it did not
  // change either.
  test("leaves a repo it could not push byte-identical, and opens nothing for it", () => {
    expect(stateOf(broken.repo)).toEqual(before.broken);
    expect(sweep.stderr).toContain("broken-remote");
    expect(gh.callsTo("pr", "create")).toHaveLength(1);
  });

  // A push that could not land is a fault, not a legitimate pass: nobody chose
  // it, and nothing in that repo will change until someone looks.
  test("counts the push it could not make as a failure, and exits non-zero for it", () => {
    expect(sweep.stdout).toContain("Done. updated=1 current=0 skipped=0 failed=1");
    expect(sweep.status).not.toBe(0);
  });

  test("restores the checkout of the repo it did push", () => {
    expect(stateOf(stale.repo)).toEqual(before.stale);
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
    before = { local: stateOf(adopter.repo), branches: gitIn(adopter.remote)("branch", "--list") };

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

  // A pretend run carries nothing, so it has no update to count — but counting
  // nothing at all is exactly the silence this contract exists to end.
  test("--dry-run reports how many repos it reached", () => {
    expect(runs.dry.stdout).toContain("Done. inspected=1 skipped=0 failed=0");
  });

  test("skips an adopter whose sweep PR is still open, naming it", () => {
    expect(runs.busy.status, runs.busy.stderr).toBe(0);
    expect(runs.busy.stdout).toContain(PR_URL);
    expect(runs.busy.stdout).toContain("Done. updated=0 current=0 skipped=1 failed=0");
    expect(shims.busy.callsTo("pr", "create")).toEqual([]);
  });

  test("leaves the adopter and its remote untouched throughout", () => {
    expect(stateOf(adopter.repo)).toEqual(before.local);
    expect(gitIn(adopter.remote)("branch", "--list")).toBe(before.branches);
    expect(answersIn(adopter.repo)).toContain(V1);
  });
});

// One fleet holding one adopter of each class, swept once. The summary line and
// the exit status are the whole contract: a reader who only sees `Done.` has to
// be able to tell a fleet that was already current from one nothing reached.
describe.skipIf(!hasCopier())("sandcastle-propagate sorts each adopter into a class", () => {
  let template;
  let searchRoot;
  let sweep;
  let gh;
  let ok;
  let dirty;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";

  beforeAll(() => {
    template = fixtureTemplate(V1);
    searchRoot = mkdtempSync(join(tmpdir(), "sandcastle-classes-"));

    ok = fixtureAdopter(searchRoot, "updates", template.src, V1, "PYTHON_VERSION=3.14");
    ok.publish();

    dirty = fixtureAdopter(searchRoot, "dirty", template.src, V1, "PYTHON_VERSION=3.14");
    dirty.publish();
    writeFileSync(join(dirty.repo, "uncommitted.txt"), "work in progress\n");

    // A breadcrumb that still names our template — so the sweep claims it — but
    // points at a path copier cannot render from. Committed, so the repo is
    // clean and the run reaches copier rather than the dirty-tree skip.
    const broken = fixtureAdopter(searchRoot, "copier-fails", template.src, V1, "PYTHON_VERSION=3.14");
    broken.publish();
    writeFileSync(
      join(broken.repo, BREADCRUMB),
      answersIn(broken.repo).replace(/^_src_path:.*$/m, "_src_path: /nonexistent/caneff/agent-skills")
    );
    broken.g("commit", "-q", "-am", "point the breadcrumb nowhere");

    template.bump(V2);
    // Installed at the tag the sweep is about to carry, so there is nothing to
    // carry: current, not updated, and emphatically not silent.
    fixtureAdopter(searchRoot, "already-current", template.src, V2, "PYTHON_VERSION=3.14").publish();

    gh = ghShim(mkdtempSync(join(tmpdir(), "sandcastle-classes-gh-")));
    sweep = propagate(template.src, searchRoot, [], { bin: gh.bin });
  });
  afterAll(() =>
    [template?.root, searchRoot, gh?.dir].forEach((d) => d && rmSync(d, { recursive: true, force: true }))
  );

  // Spelled out rather than composed from counters, so the assertion cannot
  // agree with the script by construction.
  test("names all four classes in one summary line", () => {
    expect(sweep.stdout).toContain("Done. updated=1 current=1 skipped=1 failed=1");
  });

  test("exits non-zero because one adopter faulted", () => {
    expect(sweep.status).not.toBe(0);
  });

  // The fault is carried by the exit code, not by stopping: the adopter after it
  // still got its PR.
  test("sweeps the rest of the fleet past the fault", () => {
    expect(() => gitIn(ok.remote)("rev-parse", `refs/heads/${V2_BRANCH}`)).not.toThrow();
    expect(gh.callsTo("pr", "create")).toHaveLength(1);
  });

  test("leaves the dirty adopter's uncommitted work alone", () => {
    expect(gitIn(dirty.repo)("status", "--porcelain")).toContain("uncommitted.txt");
    expect(answersIn(dirty.repo)).toContain(V1);
  });
});

// A sweep that matched nothing is the #93 stale-copy bug's signature: it printed
// a clean summary and exited 0 while walking past every repo in the fleet. Both
// ways of matching nothing are errors, and they are told apart — a wrong search
// root and a wrong filter are different mistakes to go fix.
describe("sandcastle-propagate matches no adopter", () => {
  let template;
  let empty;
  let foreign;
  let gh;

  beforeAll(() => {
    template = fixtureTemplate("sandcastle-template/v1");
    empty = mkdtempSync(join(tmpdir(), "sandcastle-none-"));
    // A breadcrumb, just not one of ours: the search root is right, the fleet is
    // simply somebody else's.
    foreign = mkdtempSync(join(tmpdir(), "sandcastle-foreign-"));
    mkdirSync(join(foreign, "other-repo"));
    writeFileSync(join(foreign, "other-repo", BREADCRUMB), "_src_path: gh:someone/other-template\n");
    gh = ghShim(mkdtempSync(join(tmpdir(), "sandcastle-none-gh-")));
  });
  afterAll(() =>
    [template?.root, empty, foreign, gh?.dir].forEach((d) => d && rmSync(d, { recursive: true, force: true }))
  );

  test("fails naming the search root when it finds no breadcrumb at all", () => {
    const sweep = propagate(template.src, empty, [], { bin: gh.bin });
    expect(sweep.status).not.toBe(0);
    expect(sweep.stderr).toContain(empty);
    expect(sweep.stderr).toMatch(/no \.copier-answers\.yml/);
  });

  // Distinct from the line above, because the fix is different: breadcrumbs are
  // here, none of them are ours.
  test("fails differently when it finds breadcrumbs but none name this template", () => {
    const sweep = propagate(template.src, foreign, [], { bin: gh.bin });
    expect(sweep.status).not.toBe(0);
    expect(sweep.stderr).toContain("1 .copier-answers.yml");
    expect(sweep.stderr).toContain("none naming caneff/agent-skills");
  });

  // `--divergence` exits 0 whatever it reports — but reporting on nobody is not
  // a finding, it is the same broken search.
  test("fails a --divergence run that matched nobody, needing no gh to do it", () => {
    const report = propagate(template.src, empty, ["--divergence"]);
    expect(report.status).not.toBe(0);
    expect(report.stderr).toContain(empty);
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

  test("says how many repos it reported on, both of them", () => {
    expect(report.stdout).toContain("Done. inspected=2 skipped=0 failed=0");
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
