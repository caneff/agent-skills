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
    // Appended to a file the render CARRIES: CONTEXT.md was withdrawn (#182), so
    // bumping it would tag a new version no adopter can see any difference in.
    bump(next) {
      appendFileSync(
        join(src, "setup-sandcastle", "templates", ".sandcastle", "CODING_STANDARDS.md"),
        "\n"
      );
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

// The healthy fleet, asserted green. Every other fixture here proves the sweep
// notices trouble; this one proves it stays quiet when there is none — the case
// the two-counter summary could not express at all.
describe.skipIf(!hasCopier())("sandcastle-propagate sweeps a fleet with nothing to do", () => {
  let template;
  let searchRoot;
  let gh;
  let idle;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";
  let allCurrent;
  let withDirty;

  beforeAll(() => {
    template = fixtureTemplate(V1);
    searchRoot = mkdtempSync(join(tmpdir(), "sandcastle-idle-"));
    template.bump(V2);
    // Both installed at the tag the sweep will target: a fleet that is done.
    fixtureAdopter(searchRoot, "current-one", template.src, V2, "PYTHON_VERSION=3.14").publish();
    idle = fixtureAdopter(searchRoot, "current-two", template.src, V2, "PYTHON_VERSION=3.14");
    idle.publish();

    gh = ghShim(mkdtempSync(join(tmpdir(), "sandcastle-idle-gh-")));
    allCurrent = propagate(template.src, searchRoot, [], { bin: gh.bin });
    // Now one of them has a human mid-edit. Nothing else about the fleet moved,
    // so the only difference between the two runs is the dirty tree.
    writeFileSync(join(idle.repo, "wip.txt"), "mid-edit\n");
    withDirty = propagate(template.src, searchRoot, [], { bin: gh.bin });
  });
  afterAll(() =>
    [template?.root, searchRoot, gh?.dir].forEach((d) => d && rmSync(d, { recursive: true, force: true }))
  );

  test("reports an all-current fleet as current, and exits 0", () => {
    expect(allCurrent.stdout).toContain("Done. updated=0 current=2 skipped=0 failed=0");
    expect(allCurrent.status, allCurrent.stderr).toBe(0);
  });

  // Deliberate: a status that goes red because someone has work in progress is a
  // status people learn to ignore.
  test("still exits 0 when a working tree is dirty, counting it as a skip", () => {
    expect(withDirty.stdout).toContain("Done. updated=0 current=1 skipped=1 failed=0");
    expect(withDirty.status, withDirty.stderr).toBe(0);
  });

  test("opens no PR for a fleet that had nothing to carry", () => {
    expect(gh.callsTo("pr", "create")).toEqual([]);
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
    expect(sweep.stderr).toContain("none of them an adopter of caneff/agent-skills");
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
// A marker the author put a line or two above the divergence it explains, rather
// than touching it. Wrapped prose produces this constantly: a marker comment,
// then a line that happens to match the render, then the edited one.
const REASON_APART = "the lesson pages need a browser to photograph";

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
    appendFileSync(
      sand("CODING_STANDARDS.md"),
      "\nA local paragraph nobody marked.\n++ not a header\n-- nor this\n"
    );
    // Marked at a distance, at exactly the reach. The marker goes in at line 3;
    // lines 4 and 5 are left as rendered; line 6 is edited. `--unified=0` splits
    // marker and divergence into separate hunks, three lines apart — the widest
    // gap a reason crosses. Both positions are relative to the splice, so
    // rewriting bot-setup.md upstream cannot move them.
    const near = readFileSync(sand("bot-setup.md"), "utf8").split("\n");
    near.splice(2, 0, `<!-- sandcastle:local — ${REASON_APART} -->`);
    near[5] += " Locally edited.";
    // A third edit three lines past that one. It is in reach of the hunk above
    // it, but that hunk only borrowed its reason — so nothing should arrive
    // here, and a reason cannot walk down a densely edited file.
    near[8] += " Also unexplained.";
    writeFileSync(sand("bot-setup.md"), near.join("\n"));
    // One line further and the reason does not travel: same shape, gap of four.
    // This is the pair that pins the reach — without it the distance could be
    // any number at all and both tests would still pass.
    const far = readFileSync(sand("pr-prompt.md"), "utf8").split("\n");
    far.splice(2, 0, `<!-- sandcastle:local — ${REASON_APART} -->`);
    far[6] += " Locally edited.";
    writeFileSync(sand("pr-prompt.md"), far.join("\n"));
    // Adopter-added: no counterpart in the render at all.
    writeFileSync(sand("extra.mts"), "export const local = 1;\n");
    diverged.publish();
    // Written after the commit, so both are untracked — the orchestrator's own
    // runtime output looks exactly like this. `logs/` the rendered `.gitignore`
    // already ignores; `scratch.mts` it does not, and an unignored addition is
    // still divergence whether or not git tracks it yet.
    mkdirSync(sand("logs"), { recursive: true });
    writeFileSync(sand("logs/run.log"), "noise the tool wrote itself\n");
    writeFileSync(sand("scratch.mts"), "export const scratch = 1;\n");

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

  // A report changes nothing, so nothing it meets can be worth blocking on. It
  // counts the fault and says so; the exit status stays 0 for the reader who
  // runs this before deciding whether to sweep at all.
  test("counts a breadcrumb outside any git repo without exiting non-zero", () => {
    const orphan = mkdtempSync(join(tmpdir(), "sandcastle-orphan-"));
    writeFileSync(join(orphan, BREADCRUMB), "_src_path: gh:caneff/agent-skills\n");
    const run = propagate(template.src, orphan, ["--divergence"]);
    expect(run.stdout).toContain("failed=1");
    expect(run.status, run.stderr).toBe(0);
    rmSync(orphan, { recursive: true, force: true });
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

  // `--unified=0` makes a hunk of every contiguous run of changed lines, so a
  // marker with even one untouched line under it lands in a hunk of its own and
  // the divergence below reads UNMARKED. The reason is right there in the file;
  // a report that calls it unexplained sends a reader to look for something they
  // already have.
  test("carries a marker across the hunk boundary to the divergence below it", () => {
    const botSetup = lines("diverged").filter((l) => l.includes("bot-setup.md"));
    // Two hunks, not one — the split this is about really did happen.
    expect(botSetup.length).toBeGreaterThan(1);
    const edited = botSetup.find((l) => /bot-setup\.md:6\s/.test(l));
    expect(edited).toBeDefined();
    // `endsWith`, not `toContain`: the reason must stop at the end of the prose.
    // A marker written as an HTML comment ends `-->`, and a report that prints
    // the closer is showing the reader the syntax instead of the reason.
    expect(edited.endsWith(REASON_APART)).toBe(true);
  });

  // The other half of the same rule, one line further out. A reason explains
  // what is next to it, not the rest of the file — and this is the case that
  // pins the reach to a number rather than to "somewhere between 2 and a lot".
  test("does not carry it one line further than that", () => {
    const prPrompt = lines("diverged").filter((l) => l.includes("pr-prompt.md"));
    const edited = prPrompt.find((l) => /pr-prompt\.md:7\s/.test(l));
    expect(edited).toBeDefined();
    expect(edited.endsWith("UNMARKED")).toBe(true);
  });

  // A hunk that inherited a reason must not re-export it. Otherwise a file with
  // an edit every couple of lines carries one marker to the bottom, which is
  // exactly what the reach exists to prevent.
  test("does not relay an inherited reason to the hunk after it", () => {
    const relayed = lines("diverged").find((l) => /bot-setup\.md:9\s/.test(l));
    expect(relayed).toBeDefined();
    expect(relayed.endsWith("UNMARKED")).toBe(true);
  });

  test("reports an unmarked hunk with its file, line and size", () => {
    expect(lineFor("CODING_STANDARDS.md")).toMatch(
      /\.sandcastle\/CODING_STANDARDS\.md:\d+\s+\+\d+ -\d+\s+UNMARKED$/
    );
  });

  test("reports an adopter-added file as its own NEW line", () => {
    expect(lineFor("extra.mts")).toMatch(/\.sandcastle\/extra\.mts\s+NEW\s+UNMARKED$/);
  });

  // The orchestrator writes logs, `.env` and scratch files into its own
  // directory. Those are the adopter's runtime output, not its divergence from
  // the template, and the repo's own git already says so.
  test("says nothing about a file the adopter's git ignores", () => {
    expect(lineFor("logs/run.log")).toBeUndefined();
    // The real edits in the same repo survive the filter — it drops noise only.
    expect(lineFor("CODING_STANDARDS.md")).toBeDefined();
  });

  test("reports an untracked file that is not ignored as NEW UNMARKED", () => {
    expect(lineFor("scratch.mts")).toMatch(/\.sandcastle\/scratch\.mts\s+NEW\s+UNMARKED$/);
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

// A linked worktree carries a checked-out copy of the repo's own breadcrumb, so
// the walk finds it wherever that worktree happens to sit — nothing constrains
// the depth. Sweeping it would open a pull request out of someone's in-progress
// branch (#194).
describe.skipIf(!hasCopier())("sandcastle-propagate meets a linked worktree", () => {
  let template;
  let searchRoot;
  let sweep;
  let gh;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";

  beforeAll(() => {
    template = fixtureTemplate(V1);
    searchRoot = mkdtempSync(join(tmpdir(), "sandcastle-worktree-"));

    const adopter = fixtureAdopter(searchRoot, "has-worktree", template.src, V1, "PYTHON_VERSION=3.14");
    // Ignored the way an adopter ignores its own worktree dir. Unignored, it
    // reads as an untracked file and the sweep skips the repo as dirty before it
    // ever reaches the worktree.
    writeFileSync(join(adopter.repo, ".gitignore"), "worktrees/\n");
    adopter.publish();
    // Two levels below the repo root, so its breadcrumb lands at the same depth
    // the walk reaches for an adopter's own.
    adopter.g("worktree", "add", "-q", "-b", "side", join(adopter.repo, "worktrees", "wip"));

    template.bump(V2);
    gh = ghShim(mkdtempSync(join(tmpdir(), "sandcastle-worktree-gh-")));
    sweep = propagate(template.src, searchRoot, [], { bin: gh.bin });
  });
  afterAll(() =>
    [template?.root, searchRoot, gh?.dir].forEach((d) => d && rmSync(d, { recursive: true, force: true }))
  );

  test("sweeps the repo once, as itself", () => {
    expect(sweep.stdout).toContain("Done. updated=1 current=0 skipped=0 failed=0");
    expect(sweep.status, sweep.stderr).toBe(0);
    expect(gh.callsTo("pr", "create")).toHaveLength(1);
  });

  test("never names the worktree as an adopter of its own", () => {
    expect(sweep.stdout).not.toContain("== wip ");
  });

  // The worktree is passed over, not counted — so a search root narrowed onto
  // one alone has matched no adopter, and that is the error it already is. A
  // clean all-zero summary here would be the #93 false green again.
  test("fails a run whose search root holds only the worktree", () => {
    const only = propagate(template.src, join(searchRoot, "has-worktree", "worktrees"), [], { bin: gh.bin });
    expect(only.status).not.toBe(0);
    expect(only.stderr).toContain("caneff/agent-skills");
  });
});
