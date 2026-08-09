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

describe.skipIf(!hasCopier())("sandcastle-propagate sweeps the adopters it finds", () => {
  let srcRoot;
  let searchRoot;
  let sweep;
  const V1 = "sandcastle-template/v1";
  const V2 = "sandcastle-template/v2";
  const adopter = (name) => join(searchRoot, name);

  beforeAll(() => {
    // The script only sweeps a breadcrumb whose `_src_path` names our template,
    // and copier records that path verbatim — so the fixture source has to LIVE
    // at a caneff/agent-skills path.
    srcRoot = mkdtempSync(join(tmpdir(), "sandcastle-prop-src-"));
    const src = join(srcRoot, "caneff", "agent-skills");
    mkdirSync(src, { recursive: true });
    cpSync(join(repoRoot, "copier.yml"), join(src, "copier.yml"));
    cpSync(join(repoRoot, "setup-sandcastle", "templates"), join(src, "setup-sandcastle", "templates"), {
      recursive: true,
    });
    const gsrc = initRepo(src);
    gsrc("add", "-A");
    gsrc("commit", "-q", "-m", "v1");
    gsrc("tag", V1);

    // Two adopters side by side, each installed at v1 with its own bare remote:
    // one python (its version must survive), one node (never asked for one).
    searchRoot = mkdtempSync(join(tmpdir(), "sandcastle-prop-adopters-"));
    for (const [name, data] of [
      ["py-adopter", "PYTHON_VERSION=3.14"],
      ["node-adopter", "LANGUAGE=node"],
    ]) {
      const repo = adopter(name);
      mkdirSync(repo);
      const g = initRepo(repo);
      writeFileSync(join(repo, "README.md"), `# ${name}\n`);
      g("add", "-A");
      g("commit", "-q", "-m", "init adopter");
      execFileSync("copier", ["copy", "--defaults", "--vcs-ref", V1, "--data", data, src, repo], {
        encoding: "utf8",
      });
      // The live node adopter reached today's template through the one-time
      // LANGUAGE correction and still carries the empty answer that correction
      // left behind. Start from that state, not from a clean node install, so
      // the sweep has a stale key to leave alone.
      if (name === "node-adopter") appendFileSync(join(repo, BREADCRUMB), "PYTHON_VERSION: ''\n");
      g("add", "-A");
      g("commit", "-q", "-m", "install sandcastle");
      const remote = mkdtempSync(join(tmpdir(), `sandcastle-prop-${name}-remote-`));
      execFileSync("git", ["init", "-q", "--bare", "-b", "main", remote]);
      g("remote", "add", "origin", remote);
      g("push", "-q", "-u", "origin", "main");
    }

    // The template moves on, so there is something for the sweep to carry.
    appendFileSync(join(src, "setup-sandcastle", "templates", ".sandcastle", "CONTEXT.md"), "\n");
    gsrc("commit", "-q", "-am", "v2");
    gsrc("tag", V2);

    sweep = spawnSync("bash", [SCRIPT], {
      encoding: "utf8",
      env: { ...process.env, SKILLS_REPO: src, SEARCH_ROOT: searchRoot },
    });
  });
  afterAll(() => [srcRoot, searchRoot].forEach((d) => d && rmSync(d, { recursive: true, force: true })));

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

  // The harm the re-assert did: on a node adopter the lookup came back empty and
  // the script fed an answer back in that the template no longer asks for.
  test("never puts a Python version into a node adopter's breadcrumb", () => {
    expect(answersIn(adopter("node-adopter"))).not.toMatch(/PYTHON_VERSION/);
  });
});
