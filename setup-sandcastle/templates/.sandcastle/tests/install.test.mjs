import { test, expect, describe } from "vitest";
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { hasCopier, preflightFixture } from "./render-fixture.mjs";

// `install` is driven end to end as an agent runs it — `spawnSync` against a
// temp repo, asserting exit status and stdout only, never internals. The
// fixture shims `PATH` and `HOME`, so preflight runs on a machine with no
// Docker, no copier and no `tdd` skill.
const here = dirname(fileURLToPath(import.meta.url));
// tests/ -> .sandcastle/ -> templates/ -> setup-sandcastle/ -> repo root
const repoRoot = join(here, "..", "..", "..", "..");

describe("the language arm", () => {
  test("no arm is refused, naming both valid values", () => {
    const f = preflightFixture(repoRoot, "python");
    const r = f.run([]);
    expect(r.status).not.toBe(0);
    expect(r.stdout).toContain("install <python|node>");
  });

  test("an unrecognised arm is refused, naming both valid values", () => {
    const f = preflightFixture(repoRoot, "python");
    const r = f.run(["rust", "--preflight"]);
    expect(r.status).not.toBe(0);
    expect(r.stdout).toContain("install <python|node>");
  });

  test("an unrecognised flag is refused rather than ignored", () => {
    const f = preflightFixture(repoRoot, "python");
    const r = f.run(["python", "--dry-run", "--preflight"]);
    expect(r.status).not.toBe(0);
    expect(r.stdout).toContain("unknown flag --dry-run");
  });
});

// Each row breaks exactly one prereq and names the message that must come
// back. The messages belong to `install`, and #167 drops SKILL.md's copy of
// them, so this table becomes the only thing holding them still — hence full
// coverage with exact matches rather than a sample.
const eachRow = (rows, arm) =>
  test.each(rows)("$what", ({ break: breakIt, says }) => {
    const f = preflightFixture(repoRoot, arm);
    breakIt(f);
    const r = f.run();
    expect(r.status).not.toBe(0);
    expect(r.stdout).toContain(says);
  });

const SHARED = [
  {
    what: "the tdd skill is not installed",
    break: (f) => rmSync(join(f.home, ".claude", "skills", "tdd"), { recursive: true }),
    says: "install the tdd skill first",
  },
  {
    what: "docker info fails",
    break: (f) => f.shim("docker", "exit 1"),
    says: "start Docker first: agents run in Docker sandboxes",
  },
  {
    what: "node is not on PATH",
    break: (f) => rmSync(join(f.bin, "node")),
    says: "no `node` on PATH",
  },
  {
    what: "npx is not on PATH",
    break: (f) => rmSync(join(f.bin, "npx")),
    says: "no `npx` on PATH",
  },
  {
    what: "copier is not installed",
    break: (f) => rmSync(join(f.bin, "copier")),
    says: "uv tool install copier",
  },
  {
    what: "the target is not a git repo",
    break: (f) => rmSync(join(f.repo, ".git"), { recursive: true }),
    says: "not a git repo",
  },
  {
    what: "the target has no PR CI workflow",
    break: (f) => rmSync(join(f.repo, ".github"), { recursive: true }),
    says: "Sandcastle needs a PR CI workflow",
  },
  {
    what: "the target has no CODING_STANDARDS.md",
    break: (f) => rmSync(join(f.repo, "CODING_STANDARDS.md")),
    says: "Sandcastle needs `CODING_STANDARDS.md`",
  },
  {
    what: "the target has no AGENTS.md",
    break: (f) => rmSync(join(f.repo, "AGENTS.md")),
    says: "Sandcastle needs `AGENTS.md`",
  },
];

describe.each(["python", "node"])("shared prereqs, %s arm", (arm) => eachRow(SHARED, arm));

// `just --list` is asserted past `check` deliberately: a repo may define one
// monolithic `check` with no separate `lint` or `typecheck`, and the
// per-commit fast check would then call a recipe that does not exist.
const recipes = (...names) =>
  `printf "Available recipes:\\n${names.map((n) => `    ${n}\\n`).join("")}"`;

const PYTHON = [
  {
    what: "the root has no .python-version",
    break: (f) => rmSync(join(f.repo, ".python-version")),
    says: "no `.python-version`",
  },
  {
    what: "just is not on PATH",
    break: (f) => rmSync(join(f.bin, "just")),
    says: "no `just` on PATH",
  },
  {
    what: "just has no check recipe",
    break: (f) => f.shim("just", recipes("lint", "typecheck")),
    says: "no `just check` recipe — run `/setup-python-repo` first",
  },
  {
    what: "just has no lint recipe",
    break: (f) => f.shim("just", recipes("check", "typecheck")),
    says: "`just` has no `lint` recipe; the per-commit fast check calls it",
  },
  {
    what: "just has no typecheck recipe",
    break: (f) => f.shim("just", recipes("check", "lint")),
    says: "`just` has no `typecheck` recipe; the per-commit fast check calls it",
  },
];

// The Node arm's entire difference at install time is its prereq list, so its
// coverage is its preflight — no render, no image.
const scripts = (obj) => (f) =>
  writeFileSync(join(f.repo, "package.json"), JSON.stringify({ scripts: obj }, null, 2) + "\n");

const NODE = [
  {
    what: "the root has no package.json",
    break: (f) => rmSync(join(f.repo, "package.json")),
    says: "no `package.json`: Sandcastle's Node arm gates on npm scripts",
  },
  {
    what: "package.json defines no lint script",
    break: scripts({ typecheck: "x", test: "x" }),
    says: "`package.json` defines no `lint` script; the gate and the per-commit fast check both call `npm run lint`",
  },
  {
    what: "package.json defines no typecheck script",
    break: scripts({ lint: "x", test: "x" }),
    says: "`package.json` defines no `typecheck` script; the gate and the per-commit fast check both call `npm run typecheck`",
  },
  {
    what: "package.json defines no test script",
    break: scripts({ lint: "x", typecheck: "x" }),
    says: "`package.json` defines no `test` script; the gate calls `npm run test`",
  },
  {
    // The gate calls `npm run lint`; a dependency of that name does not answer.
    what: "package.json names lint somewhere other than its scripts block",
    break: (f) =>
      writeFileSync(
        join(f.repo, "package.json"),
        JSON.stringify(
          { devDependencies: { lint: "^1.0.0" }, scripts: { typecheck: "x", test: "x" } },
          null,
          2
        ) + "\n"
      ),
    says: "`package.json` defines no `lint` script",
  },
];

describe("python arm prereqs", () => eachRow(PYTHON, "python"));

describe("node arm prereqs", () => eachRow(NODE, "node"));

// Every path in the repo with its bytes, so "mutated nothing" is asserted
// against the whole tree rather than a couple of files we thought to check.
function snapshot(dir) {
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => {
      const p = join(e.parentPath, e.name);
      return `${p}\n${readFileSync(p, "utf8")}`;
    })
    .sort()
    .join("\n---\n");
}

describe.each(["python", "node"])("a ready repo, %s arm", (arm) => {
  test("passes preflight and writes nothing", () => {
    const f = preflightFixture(repoRoot, arm);
    const before = snapshot(f.repo);
    const r = f.run();
    expect(r.stdout).toContain("preflight passed");
    expect(r.status).toBe(0);
    expect(snapshot(f.repo)).toBe(before);
  });
});

describe("a repo that already carries a render", () => {
  // Locked decision 13 — never re-render over an adopter. Preflight enforces
  // it rather than leaving it to prose, before copier is reached.
  test.each([".copier-answers.yml", join(".sandcastle", "main.mts")])(
    "is refused, naming the %s it found",
    (marker) => {
      const f = preflightFixture(repoRoot, "python");
      mkdirSync(dirname(join(f.repo, marker)), { recursive: true });
      writeFileSync(join(f.repo, marker), "x\n");
      const r = f.run();
      expect(r.status).not.toBe(0);
      expect(r.stdout).toContain("already carries a Sandcastle render");
      expect(r.stdout).toContain(marker);
    }
  );
});

// Both checks are pulled forward into preflight (#151): a missing source found
// after the render costs a re-render to recover from, and a stageable `.env` is
// the one failure that leaks credentials, so neither waits for copier.
describe("--env-from", () => {
  test("a source path that does not exist is refused", () => {
    const f = preflightFixture(repoRoot, "python");
    const r = f.run(["python", "--preflight", "--env-from", join(f.root, "nope.env")]);
    expect(r.status).not.toBe(0);
    expect(r.stdout).toContain("no file at");
    expect(r.stdout).toContain("nope.env");
  });

  test("a copy that would be stageable is refused rather than made", () => {
    // Tracked beats ignored in git, so the render's own `.sandcastle/.gitignore`
    // would not cover this one — the secret would land in `git add .`.
    const f = preflightFixture(repoRoot, "python");
    const source = join(f.root, "source.env");
    writeFileSync(source, "GH_TOKEN=shh\n");
    mkdirSync(join(f.repo, ".sandcastle"), { recursive: true });
    writeFileSync(join(f.repo, ".sandcastle", ".env"), "");
    execFileSync("git", ["-C", f.repo, "add", "-f", join(".sandcastle", ".env")]);
    const r = f.run(["python", "--preflight", "--env-from", source]);
    expect(r.status).not.toBe(0);
    expect(r.stdout).toContain("already tracked by git");
    expect(readFileSync(join(f.repo, ".sandcastle", ".env"), "utf8")).toBe("");
  });
});

// One non-zero exit covers every failure (#151), so the message carries the
// whole classification — which step was reached, and whether re-running is
// safe. Driven with the fake `copier`, so it needs nothing real installed.
test("a failed render names the step and says re-running is not safe", () => {
  const f = preflightFixture(repoRoot, "python");
  const before = snapshot(f.repo);
  f.shim("copier", "exit 1");
  const r = f.run(["python"]);
  expect(r.status).not.toBe(0);
  expect(r.stdout).toContain("step 1 (render) failed");
  expect(r.stdout).toContain("NOT safe to re-run");
  expect(snapshot(f.repo)).toBe(before);
});

// The one end-to-end run: real copier, real `npm install`, real `npx tsc`. The
// install is not stubbed anywhere — a flag that skipped the slow part would
// mean the asserted path is not the shipped path (#154).
describe.skipIf(!hasCopier())("a full install, python arm", () => {
  test("renders, wires the host runtime, typechecks and hands off", { timeout: 600_000 }, () => {
    const f = preflightFixture(repoRoot, "python", { realTools: true });
    const r = f.run(["python"]);
    expect(r.stdout + r.stderr).toContain("install complete");
    expect(r.status).toBe(0);

    const pkg = JSON.parse(readFileSync(join(f.repo, "package.json"), "utf8"));
    expect(pkg.scripts.sandcastle).toBe("npx tsx .sandcastle/main.mts");
    expect(readFileSync(join(f.repo, "CLAUDE.md"), "utf8")).toBe(
      "@AGENTS.md\n@CODING_STANDARDS.md\n"
    );
    // Run without `--env-from`, so the handoff owes the reader the `.env`.
    expect(r.stdout).toContain(".sandcastle/.env");

    // Locked decision 13, asserted against a real render rather than a marker
    // file: the second run refuses instead of re-rendering over the first.
    const again = f.run(["python"]);
    expect(again.status).not.toBe(0);
    expect(again.stdout).toContain("already carries a Sandcastle render");
  });
});

test("no check reads an absolute path outside $HOME", () => {
  const source = readFileSync(join(repoRoot, "setup-sandcastle", "install"), "utf8");
  const absolute = source
    .split("\n")
    .filter((line) => !line.startsWith("#"))
    .filter((line) => /(^|[^\w$."'/])\/(usr|bin|etc|opt|var|home|Users|Applications)\//.test(line));
  expect(absolute).toEqual([]);
});
