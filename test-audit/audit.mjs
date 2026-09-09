#!/usr/bin/env node
/**
 * Pass one of test-audit for JS/TS: the node sibling of audit.py.
 *
 * Scans vitest-style test files on a real @babel/parser AST and emits the same
 * `file:line: <smell>` candidates audit.py does for pytest. This script never
 * classifies — it only surfaces candidates for the judgment pass (SKILL.md).
 *
 * Five smells, on vitest and node:test alike —
 *   1. assertion-free   — the test body has no `expect(...)`/`assert.*` call.
 *   2. tautology        — `expect(x).toBe(x)` / `assert.equal(x, x)`.
 *   3. empty/skipped    — empty body, or `.skip`/`.todo`, or a bodyless `it`.
 *   4. mock-the-world   — mock constructs exceed a ceiling, little real logic.
 *   5. interaction-only — every assertion only checks that a spy was called.
 *
 * audit.py keeps the pytest path untouched.
 */
import { readFileSync, readdirSync, statSync, mkdtempSync, mkdirSync, writeFileSync, rmSync, unlinkSync } from "node:fs";
import { join, basename, extname } from "node:path";
import { tmpdir } from "node:os";
import assert from "node:assert";

// --- parser bootstrap ------------------------------------------------------

let parse;
try {
  ({ parse } = await import("@babel/parser"));
} catch {
  process.stderr.write(
    "test-audit: @babel/parser is missing — run `npm ci` in test-audit/ first.\n",
  );
  process.exit(2);
}

function parseSource(source, path) {
  const ext = extname(path);
  const plugins = [];
  if (ext === ".ts" || ext === ".mts" || ext === ".cts") {
    plugins.push("typescript");
  } else if (ext === ".tsx") {
    plugins.push("typescript", "jsx");
  } else {
    plugins.push("jsx");
  }
  // No errorRecovery: an unparseable file throws, scanFile catches it and
  // skips the file — the parity with audit.py's SyntaxError → skip.
  return parse(source, { sourceType: "module", plugins });
}

// --- AST walk --------------------------------------------------------------

function walk(node, visit) {
  if (!node || typeof node.type !== "string") return;
  visit(node);
  for (const key of Object.keys(node)) {
    if (key === "loc" || key === "start" || key === "end") continue;
    const child = node[key];
    if (Array.isArray(child)) {
      for (const c of child) if (c && typeof c.type === "string") walk(c, visit);
    } else if (child && typeof child.type === "string") {
      walk(child, visit);
    }
  }
}

/** An Identifier node's name, else null. */
function identifierName(node) {
  return node && node.type === "Identifier" ? node.name : null;
}

/** The bare callee name for an Identifier call, else null. */
function calleeName(node) {
  if (node.type !== "CallExpression") return null;
  return identifierName(node.callee);
}

/** The `object.property` root+method for a member-call (`it.skip`), else null. */
function memberCallee(node) {
  if (node.type !== "CallExpression") return null;
  const c = node.callee;
  if (c.type !== "MemberExpression") return null;
  const root = identifierName(c.object);
  const method = identifierName(c.property);
  return root && method ? { root, method } : null;
}

const TEST_ROOTS = new Set(["it", "test"]);
const SUITE_ROOTS = new Set(["describe", "it", "test"]);
// node:test hangs its lifecycle hooks off the same root as its tests
// (`test.after(...)`), so a root match alone collects a teardown hook as an
// assertion-free test (#677). A denylist, so `it.skip` and any runner variant
// (`concurrent`, `failing`) stay collected. `beforeAll`/`afterAll` are here for
// the same reason: vitest and Playwright hang them off `test` too.
const LIFECYCLE_HOOKS = new Set(["after", "before", "beforeEach", "afterEach", "beforeAll", "afterAll"]);

/** Does this CallExpression name a single test (`it`/`test`, incl. `.skip`)? */
function isTestCall(node) {
  const bare = calleeName(node);
  if (bare && TEST_ROOTS.has(bare)) return true;
  const mem = memberCallee(node);
  return !!(mem && TEST_ROOTS.has(mem.root) && !LIFECYCLE_HOOKS.has(mem.method));
}

/** The modifier on a member test call (`skip`/`todo`/`only`), else null. */
function testModifier(node) {
  const mem = memberCallee(node);
  return mem && TEST_ROOTS.has(mem.root) ? mem.method : null;
}

/** The callback function argument of a test call, else null (bodyless `it`). */
function testCallback(node) {
  for (const arg of node.arguments) {
    if (arg.type === "ArrowFunctionExpression" || arg.type === "FunctionExpression") return arg;
  }
  return null;
}

/** Every single-test CallExpression in the tree. */
function testCalls(tree) {
  const found = [];
  walk(tree, (n) => {
    if (n.type === "CallExpression" && isTestCall(n)) found.push(n);
  });
  return found;
}

// --- recognize-or-skip gate ------------------------------------------------

// A file is audited only when it looks like vitest: it names tests
// (`describe`/`it`/`test`) AND uses `expect`. Requiring `expect` is the guard
// against a homegrown harness — its custom check verb is not `expect`, so the
// file is skipped rather than flooded with false assertion-free findings. The
// cost is a vitest file whose every test is assertion-free (no `expect`
// anywhere): it is skipped too. That tradeoff is the #287 decision.
function isVitestFile(tree) {
  let hasSuite = false;
  let hasExpect = false;
  walk(tree, (n) => {
    if (n.type !== "CallExpression") return;
    const bare = calleeName(n);
    const mem = memberCallee(n);
    if ((bare && SUITE_ROOTS.has(bare)) || (mem && SUITE_ROOTS.has(mem.root))) hasSuite = true;
    if (bare === "expect") hasExpect = true;
  });
  return hasSuite && hasExpect;
}

// A file is audited as node:test only when it both imports from 'node:test'
// AND uses `assert.*` — the same false-positive guard as the vitest gate,
// applied to node's built-in runner instead of a `describe`/`it`/`expect` net.
function isNodeTestFile(tree) {
  let hasImport = false;
  let hasAssert = false;
  walk(tree, (n) => {
    if (n.type === "ImportDeclaration" && n.source.value === "node:test") hasImport = true;
    if (assertCallInfo(n)) hasAssert = true;
  });
  return hasImport && hasAssert;
}

// --- assertion vocabulary --------------------------------------------------

const EQ_MATCHERS = new Set(["toBe", "toEqual", "toStrictEqual"]);

/**
 * An `expect(...).matcher(...)` assertion is a CallExpression whose callee is a
 * MemberExpression rooted (through any chained `.not`/`.resolves`/...) at an
 * `expect(...)` call. Returns { expectCall, matcher, matcherCall } or null.
 */
function asExpectAssertion(node) {
  if (node.type !== "CallExpression" || node.callee.type !== "MemberExpression") return null;
  const matcher = identifierName(node.callee.property);
  let obj = node.callee.object;
  while (obj && obj.type === "MemberExpression") obj = obj.object; // walk past .not/.resolves
  if (obj && obj.type === "CallExpression" && calleeName(obj) === "expect") {
    return { expectCall: obj, matcher, matcherCall: node };
  }
  return null;
}

const ASSERT_EQ_MATCHERS = new Set(["equal", "strictEqual", "deepEqual", "deepStrictEqual"]);

/**
 * A `node:assert` call: `assert.equal(a, b)` (member form) or the bare
 * `assert(x)` shorthand for `assert.ok(x)`. Returns { matcher, args } or null.
 */
function assertCallInfo(node) {
  if (node.type !== "CallExpression") return null;
  const c = node.callee;
  if (c.type === "MemberExpression" && identifierName(c.object) === "assert" && identifierName(c.property)) {
    return { matcher: identifierName(c.property), args: node.arguments };
  }
  if (identifierName(c) === "assert") {
    return { matcher: "ok", args: node.arguments };
  }
  return null;
}

// Every assertion in a test body, `expect(...)` chains and `assert.*` calls
// alike, normalized to { isEq, actual, expected } — the shape both the
// assertion-free and tautology detectors need, regardless of vocabulary.
function assertionsIn(func) {
  const out = [];
  walk(func.body, (n) => {
    const e = asExpectAssertion(n);
    if (e) {
      out.push({
        kind: "expect",
        matcher: e.matcher,
        isEq: EQ_MATCHERS.has(e.matcher),
        actual: e.expectCall.arguments[0],
        expected: e.matcherCall.arguments[0],
      });
      return;
    }
    const a = assertCallInfo(n);
    if (a) {
      out.push({
        kind: "assert",
        matcher: a.matcher,
        isEq: ASSERT_EQ_MATCHERS.has(a.matcher),
        actual: a.args[0],
        expected: a.args[1],
        args: a.args,
      });
    }
  });
  return out;
}

// --- detectors -------------------------------------------------------------

// Every detector takes the same pair — the test CallExpression and the file
// source — mirroring audit.py's uniform `detector(func)`. Each pulls what it
// needs (callback, source) internally, so the scan loop stays a plain
// `for (smell, detector) if detector(call, source)`.

function isAssertionFree(call) {
  const cb = testCallback(call);
  // No callback (a bodyless `it`) is empty/skipped's concern, not this one.
  if (!cb) return false;
  return assertionsIn(cb).length === 0;
}

function isTautology(call, source) {
  const cb = testCallback(call);
  if (!cb) return false;
  for (const { isEq, actual, expected } of assertionsIn(cb)) {
    if (!isEq) continue;
    if (actual && expected && sameSource(actual, expected, source)) return true;
  }
  return false;
}

function isEmptyOrSkipped(call) {
  const mod = testModifier(call); // it.skip / it.todo / it.only
  if (mod === "skip" || mod === "todo") return true;
  const cb = testCallback(call);
  if (!cb) return true; // `it('todo')` with no callback
  return cb.body.type === "BlockStatement" && cb.body.body.length === 0;
}

// ponytail: compare two expression subtrees by their exact source slice.
// `expect(x).toBe(x)` — both `x` occupy identical source, so the equality can
// never fail. Robust enough for the literal self-comparison; the semantic
// re-implementation form is judgment-pass territory (mirrors audit.py).
function sameSource(a, b, source) {
  return source.slice(a.start, a.end) === source.slice(b.start, b.end);
}

// ponytail: 3 is the ceiling, matching audit.py's MOCK_CEILING. Below it, a
// test with one or two mocked collaborators and real logic in between is
// normal isolation, not a smell.
const MOCK_CEILING = 3;

/** The dotted name chain of a (possibly nested) MemberExpression callee, e.g.
 * `t.mock.fn` -> ["t", "mock", "fn"]. Null if any link isn't a plain name. */
function memberPath(node) {
  const parts = [];
  let n = node;
  while (n && n.type === "MemberExpression") {
    if (n.property.type !== "Identifier") return null;
    parts.unshift(n.property.name);
    n = n.object;
  }
  if (!n || n.type !== "Identifier") return null;
  parts.unshift(n.name);
  return parts;
}

const NODE_MOCK_ROOTS = new Set(["fn", "method", "module", "timers"]);

/** A mock-construction call: vitest `vi.fn/vi.mock/vi.spyOn`, node:test
 * `mock.fn/mock.method/mock.module/mock.timers`, or any `t.mock.*` call. Also
 * matches a chained mock-config call on top of one of those (`vi.fn()
 * .mockReturnValue(5)`), so the config half of the chain doesn't get counted
 * as real logic. */
function isMockConstructCall(node) {
  if (node.type !== "CallExpression") return false;
  const path = memberPath(node.callee);
  if (path && path.length >= 2) {
    if (path[0] === "vi" && ["fn", "mock", "spyOn"].includes(path[1])) return true;
    if (path[0] === "mock" && NODE_MOCK_ROOTS.has(path[1])) return true;
    if (path[0] === "t" && path[1] === "mock") return true;
  }
  const obj = node.callee.type === "MemberExpression" ? node.callee.object : null;
  return !!(obj && obj.type === "CallExpression" && isMockConstructCall(obj));
}

function isAssertionCall(node) {
  return calleeName(node) === "expect" || !!asExpectAssertion(node) || !!assertCallInfo(node);
}

function isMockTheWorld(call) {
  const cb = testCallback(call);
  if (!cb) return false;
  let mockCalls = 0;
  let realCalls = 0;
  walk(cb.body, (n) => {
    if (n.type !== "CallExpression") return;
    if (isMockConstructCall(n)) {
      mockCalls += 1;
    } else if (!isAssertionCall(n)) {
      realCalls += 1;
    }
  });
  return mockCalls >= MOCK_CEILING && mockCalls > realCalls;
}

// vitest's spy-call-check matcher family, plus node:test's best-effort
// equivalent: an `assert.*` whose argument source references `.mock.calls`
// or `.mock.callCount(`.
const INTERACTION_MATCHERS = new Set([
  "toHaveBeenCalled",
  "toHaveBeenCalledTimes",
  "toHaveBeenCalledWith",
  "toHaveBeenLastCalledWith",
  "toHaveReturned",
  "toHaveReturnedTimes",
  "toHaveReturnedWith",
  "toHaveLastReturnedWith",
]);
const MOCK_CALLS_RE = /\.mock\.(calls\b|callCount\s*\()/;

function isSpyCheck(assertion, source) {
  if (assertion.kind === "expect") return INTERACTION_MATCHERS.has(assertion.matcher);
  return (assertion.args || []).some(
    (arg) => arg && MOCK_CALLS_RE.test(source.slice(arg.start, arg.end)),
  );
}

// Every assertion is a spy-call check (reuses assertionsIn() so an outcome
// assertion mixed in with spy checks correctly stops this from firing).
function isInteractionOnly(call, source) {
  const cb = testCallback(call);
  if (!cb) return false;
  const assertions = assertionsIn(cb);
  if (assertions.length === 0) return false;
  return assertions.every((a) => isSpyCheck(a, source));
}

const DETECTORS = [
  ["assertion-free test", isAssertionFree],
  ["tautology", isTautology],
  ["empty/skipped test", isEmptyOrSkipped],
  ["mock-the-world", isMockTheWorld],
  ["interaction-only assertion", isInteractionOnly],
];

// --- scan ------------------------------------------------------------------

function lineOf(node) {
  return node.loc ? node.loc.start.line : 0;
}

function scanFile(path) {
  let source;
  try {
    source = readFileSync(path, "utf8");
  } catch {
    return [];
  }
  let tree;
  try {
    tree = parseSource(source, path);
  } catch {
    return [];
  }
  if (!isVitestFile(tree) && !isNodeTestFile(tree)) return [];
  const findings = [];
  for (const call of testCalls(tree)) {
    for (const [smell, detect] of DETECTORS) {
      if (detect(call, source)) findings.push([path, lineOf(call), smell]);
    }
  }
  return findings;
}

const EXT_RE = /\.(js|jsx|ts|tsx|mjs|cjs|mts)$/;
const FILE_RE = /\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs|mts)$/;
// Mirror of the Python family's one excluded-directory set (auditlib.py),
// regenerated by `python3 all-audits/harness/auditlib.py --write-json-mirror
// all-audits/harness/excluded-dirs.json` — never hand-edit this list here.
const PRUNE_DIRS = new Set(
  JSON.parse(readFileSync(new URL("../all-audits/harness/excluded-dirs.json", import.meta.url), "utf8")),
);

// A file is in the net if it matches `*.{test,spec}.{ext}`, or is any JS/TS
// file living under a `__tests__/` directory.
function inNet(dir, name) {
  return FILE_RE.test(name) || (basename(dir) === "__tests__" && EXT_RE.test(name));
}

function collect(root, out) {
  let entries;
  try {
    entries = readdirSync(root, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const p = join(root, e.name);
    if (e.isDirectory()) {
      if (!PRUNE_DIRS.has(e.name)) collect(p, out);
    } else if (inNet(root, e.name)) {
      out.push(p);
    }
  }
}

function scanPath(root) {
  const paths = [];
  if (statSync(root, { throwIfNoEntry: false })?.isFile()) {
    paths.push(root);
  } else {
    collect(root, paths);
  }
  paths.sort();
  const findings = [];
  for (const p of paths) findings.push(...scanFile(p));
  return findings;
}

// --- selfcheck -------------------------------------------------------------

function testCallFrom(src) {
  const tree = parseSource(src, "snippet.test.js");
  return testCalls(tree)[0];
}
function tautologyOf(src) {
  return isTautology(testCallFrom(src), src);
}
function testCallCount(src) {
  return testCalls(parseSource(src, "snippet.test.js")).length;
}

function selfcheck() {
  // 0. test-call collection: modifiers are tests, lifecycle hooks are not (#677)
  assert(testCallCount("test.after(() => { server.close(); })") === 0, "lifecycle hook is not a test call");
  assert(testCallCount("test.before(() => { server.listen(); })") === 0, "before hook is not a test call");
  assert(testCallCount("test.beforeEach(() => { reset(); })") === 0, "beforeEach hook is not a test call");
  assert(testCallCount("test.afterEach(() => { reset(); })") === 0, "afterEach hook is not a test call");
  assert(testCallCount("test.beforeAll(() => { boot(); })") === 0, "beforeAll hook is not a test call");
  assert(testCallCount("test.afterAll(() => { shutdown(); })") === 0, "afterAll hook is not a test call");
  assert(
    testCallCount("it.skip('x', () => { expect(a).toBe(b); })") === 1,
    "skip modifier is still a test call",
  );

  // 1. assertion-free
  assert(isAssertionFree(testCallFrom("it('x', () => { const y = compute(); })")), "assertion-free positive");
  assert(!isAssertionFree(testCallFrom("it('x', () => { expect(compute()).toBe(5); })")), "assertion-free negative");
  assert(
    isAssertionFree(testCallFrom("test('x', () => { const y = compute(); })")),
    "assertion-free positive (node:test)",
  );
  assert(
    !isAssertionFree(testCallFrom("test('x', () => { assert.equal(compute(), 5); })")),
    "assertion-free negative (node:test)",
  );

  // 2. tautology
  assert(tautologyOf("it('x', () => { expect(x).toBe(x); })"), "tautology positive");
  assert(!tautologyOf("it('x', () => { expect(x).toBe(5); })"), "tautology negative");
  assert(tautologyOf("test('x', () => { assert.equal(x, x); })"), "tautology positive (node:test)");
  assert(!tautologyOf("test('x', () => { assert.equal(x, 5); })"), "tautology negative (node:test)");

  // 3. empty/skipped
  assert(isEmptyOrSkipped(testCallFrom("it('x', () => {})")), "empty body positive");
  assert(isEmptyOrSkipped(testCallFrom("it.skip('x', () => { expect(a).toBe(b); })")), "skip positive");
  assert(!isEmptyOrSkipped(testCallFrom("it('x', () => { expect(a).toBe(b); })")), "empty/skipped negative");
  assert(isEmptyOrSkipped(testCallFrom("test('x', () => {})")), "empty body positive (node:test)");
  assert(
    isEmptyOrSkipped(testCallFrom("test.skip('x', () => { assert.equal(a, b); })")),
    "skip positive (node:test)",
  );
  assert(
    !isEmptyOrSkipped(testCallFrom("test('x', () => { assert.equal(a, b); })")),
    "empty/skipped negative (node:test)",
  );

  // recognize-or-skip gate
  assert(isVitestFile(parseSource("it('x', () => { expect(a).toBe(b); })", "s.test.js")), "gate recognizes vitest");
  assert(
    !isVitestFile(parseSource("harness('x', () => { check(a, b); })", "s.test.js")),
    "gate skips homegrown harness",
  );
  const nodeTestSrc =
    "import { test } from 'node:test';\nimport assert from 'node:assert';\ntest('x', () => { assert.equal(a, b); });\n";
  assert(isNodeTestFile(parseSource(nodeTestSrc, "s.test.js")), "gate recognizes node:test");
  assert(
    !isNodeTestFile(parseSource("it('x', () => { expect(a).toBe(b); })", "s.test.js")),
    "gate: vitest file is not node:test",
  );
  assert(
    !isVitestFile(parseSource(nodeTestSrc, "s.test.js")),
    "gate: node:test file is not vitest",
  );
  assert(
    !isNodeTestFile(
      parseSource("import { test } from 'node:test';\ntest('x', () => { doStuff(a, b); });\n", "s.test.js"),
    ),
    "gate skips node:test import without assert.* usage",
  );
  const foreignHarness = parseSource("harness('x', () => { check(a, b); })", "s.test.js");
  assert(
    !isVitestFile(foreignHarness) && !isNodeTestFile(foreignHarness),
    "combined gate skips a file that is neither vitest nor node:test",
  );

  // 4. mock-the-world
  assert(
    isMockTheWorld(
      testCallFrom(
        "it('x', () => { const a = vi.fn(); const b = vi.fn(); const c = vi.spyOn(obj, 'm'); subject.run(); })",
      ),
    ),
    "mock-the-world positive (vitest)",
  );
  assert(
    !isMockTheWorld(
      testCallFrom(
        "it('x', () => { const a = vi.fn(); const result = subject.compute(1, 2); expect(result).toBe(3); })",
      ),
    ),
    "mock-the-world negative (vitest)",
  );
  assert(
    isMockTheWorld(
      testCallFrom(
        "test('x', (t) => { const a = t.mock.fn(); const b = t.mock.fn(); const c = t.mock.method(obj, 'm'); subject.run(); })",
      ),
    ),
    "mock-the-world positive (node:test)",
  );
  assert(
    isMockTheWorld(
      testCallFrom(
        "it('x', () => { const a = vi.fn().mockReturnValue(1); const b = vi.fn().mockReturnValue(2); const c = vi.spyOn(obj, 'm'); subject.run(); })",
      ),
    ),
    "mock-the-world positive (vitest, chained mock config)",
  );
  assert(
    !isMockTheWorld(
      testCallFrom(
        "test('x', () => { const a = mock.fn(); const result = subject.compute(1, 2); assert.equal(result, 3); })",
      ),
    ),
    "mock-the-world negative (node:test)",
  );

  // 5. interaction-only assertion
  assert(
    isInteractionOnly(
      testCallFrom("it('x', () => { fn(); expect(fn).toHaveBeenCalled(); })"),
      "it('x', () => { fn(); expect(fn).toHaveBeenCalled(); })",
    ),
    "interaction-only positive (vitest)",
  );
  assert(
    !isInteractionOnly(
      testCallFrom("it('x', () => { const result = subject.run(); expect(result).toBe('ok'); })"),
      "it('x', () => { const result = subject.run(); expect(result).toBe('ok'); })",
    ),
    "interaction-only negative (vitest)",
  );
  {
    const src = "test('x', () => { fn(); assert.equal(fn.mock.calls.length, 1); })";
    assert(isInteractionOnly(testCallFrom(src), src), "interaction-only positive (node:test, best-effort)");
  }
  {
    const src = "test('x', () => { const result = subject.run(); assert.equal(result, 'ok'); })";
    assert(!isInteractionOnly(testCallFrom(src), src), "interaction-only negative (node:test)");
  }
  {
    // Mixing an outcome assertion in with a spy check must not fire — the
    // constraint that isInteractionOnly reuse assertionsIn() so it doesn't
    // misfire on a mixed set.
    const src =
      "it('x', () => { const result = subject.run(); expect(result).toBe('ok'); expect(fn).toHaveBeenCalled(); })";
    assert(!isInteractionOnly(testCallFrom(src), src), "interaction-only negative (vitest, mixed assertions)");
  }

  // gate mode: assertion-free only, and never a fixture.
  const tmp = mkdtempSync(join(tmpdir(), "test-audit-gate-"));
  try {
    // Every file here carries a real `expect` so the recognize-or-skip gate
    // above admits it -- a file with no assertion anywhere is skipped whole,
    // the #287 tradeoff, and the gate inherits that blind spot.
    const hollow = "it('hollow', () => { compute(); });\nit('real', () => { expect(a).toBe(1); });\n";
    mkdirSync(join(tmp, "fixtures"));
    writeFileSync(join(tmp, "fixtures", "specimen.test.js"), hollow);
    writeFileSync(join(tmp, "taut.test.js"), "it('x', () => { expect(x).toBe(x); });\n");
    // a deliberate specimen and a report-only smell: neither fails a build
    assert.deepEqual(gate(tmp), [], "gate skips fixtures and non-gated smells");
    assert(scanPath(tmp).length > 0, "the report pass still sees both");

    writeFileSync(join(tmp, "hollow.test.js"), hollow);
    const gated = gate(tmp);
    assert.equal(gated.length, 1, "gate catches the hollow test");
    assert(gated[0][0].endsWith("hollow.test.js"), "gate names the hollow test");

    unlinkSync(join(tmp, "hollow.test.js"));
    assert.deepEqual(gate(tmp), [], "gate is clean once the hollow test is gone");
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }

  process.stdout.write("ok\n");
}

// --- gate mode -------------------------------------------------------------

// The one smell a build gates on -- the Python side's GATE_SMELL, same
// reasoning: the other four still run and still fail when the behavior
// breaks, while an assertion-free test cannot fail at all.
const GATE_SMELL = "assertion-free test";

/** Does `path` lie under a `fixtures/` directory? A fixture is a deliberate
 * specimen of the smell, so the gate never counts one; the report still does. */
function underFixtures(path) {
  return path.split(/[\\/]/).includes("fixtures");
}

/** The findings that fail a build: `GATE_SMELL` only, fixtures excluded. */
function gate(root) {
  return scanPath(root).filter(([path, , smell]) => smell === GATE_SMELL && !underFixtures(path));
}

// --- main ------------------------------------------------------------------

const arg = process.argv[2];
if (arg === "--selfcheck") {
  selfcheck();
} else if (arg === "--gate") {
  const findings = gate(process.argv[3] || ".");
  for (const [path, line, smell] of findings) process.stdout.write(`${path}:${line}: ${smell}\n`);
  if (findings.length > 0) {
    process.stderr.write(
      `test-audit: ${findings.length} assertion-free test(s) -- a test that cannot fail proves nothing.\n`,
    );
    process.exit(1);
  }
} else {
  const findings = scanPath(arg || ".");
  for (const [path, line, smell] of findings) process.stdout.write(`${path}:${line}: ${smell}\n`);
  if (findings.length === 0) process.stderr.write("no mechanical smells found\n");
}
