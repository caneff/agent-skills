import { test, expect, describe, beforeAll, afterAll } from "vitest";
import { execFileSync, spawnSync } from "node:child_process";
import { appendFileSync, cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// `sandcastle-propagate` is driven end to end, as the sweep runs it: a fixture
// template repo (SKILLS_REPO), a fixture tree of adopters (SEARCH_ROOT), and a
// bare remote for each so the script's commit+push completes. We observe the
// script's stdout banner and each adopter's breadcrumb afterwards — never its
// internals.
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

// An adopter that installed the template at `ref`, with a bare remote so the
// sweep's commit+push completes.
function fixtureAdopter(searchRoot, name, src, ref, data) {
  const repo = join(searchRoot, name);
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
  return { repo, g, publish: () => {
    g("add", "-A");
    g("commit", "-q", "-m", "install sandcastle");
    // The remote lives under the fixture root so it is discarded with it. Bare,
    // so it carries no breadcrumb and the sweep's `find` walks past it.
    const remote = join(searchRoot, ".remotes", `${name}.git`);
    execFileSync("git", ["init", "-q", "--bare", "-b", "main", remote]);
    g("remote", "add", "origin", remote);
    g("push", "-q", "-u", "origin", "main");
  } };
}

const propagate = (src, searchRoot, ...args) =>
  spawnSync("bash", [SCRIPT, ...args], {
    encoding: "utf8",
    env: { ...process.env, SKILLS_REPO: src, SEARCH_ROOT: searchRoot },
  });

describe.skipIf(!hasCopier())("sandcastle-propagate sweeps the adopters it finds", () => {
  let template;
  let searchRoot;
  let sweep;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";
  const adopter = (name) => join(searchRoot, name);

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
    sweep = propagate(template.src, searchRoot);
  });
  afterAll(() => [template?.root, searchRoot].forEach((d) => d && rmSync(d, { recursive: true, force: true })));

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
    expect(answersIn(adopter("py-adopter"))).toMatch(recordedAnswer("PYTHON_VERSION", "3.14"));
  });

  // The sweep carries the template and then says what it could not carry — the
  // same report `--divergence` prints alone, per repo, after each update.
  test("prints each repo's divergence report after updating it", () => {
    expect(sweep.stdout).toMatch(/py-adopter\s+\.sandcastle\/local-only\.mts\s+NEW\s+UNMARKED/);
  });

  // The harm the re-assert did: on a node adopter the lookup came back empty and
  // the script fed an answer back in that the template no longer asks for.
  test("never puts a Python version into a node adopter's breadcrumb", () => {
    expect(answersIn(adopter("node-adopter"))).not.toMatch(/PYTHON_VERSION/);
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
    report = propagate(template.src, searchRoot, "--divergence");
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
