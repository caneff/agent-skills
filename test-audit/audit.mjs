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
import {
  accessSync,
  constants,
  readFileSync,
  readdirSync,
  statSync,
  existsSync,
  mkdtempSync,
  mkdirSync,
  chmodSync,
  writeFileSync,
  rmSync,
  unlinkSync,
} from "node:fs";
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
// node:test and Playwright hang a growing family of non-test member calls off
// the same root as their tests (`test.after(...)`, `test.describe(...)`,
// `test.use(...)`), so a root match alone collects each as a test in its own
// right -- a lifecycle hook or config call as an assertion-free/empty/skipped
// test (#677), a suite alias as a duplicate of every finding inside it
// (#679). A denylist, not an allowlist: a missed entry is a visible false
// positive, an allowlist's missed entry silently drops a real test (#679
// triage ruling). An unlisted runner variant (`concurrent`, `failing`,
// `sequential`) stays collected, and so does `it.skip`/`test.todo`.
const HOOK_METHODS = new Set(["after", "before", "beforeEach", "afterEach", "beforeAll", "afterAll"]);
// `describe`/`suite` are real evidence a file organizes tests this way (kept
// in the suite gate below) but are not themselves a test -- their nested
// tests are audited individually.
const SUITE_ALIAS_METHODS = new Set(["describe", "suite"]);
// Playwright's config, fixture and annotation calls (`use`, `setTimeout`,
// `extend`, `configure`, `slow`), `info()` (returns a value, declares
// nothing), and `step` -- unlike the rest of this set `step` does take a
// title+callback, but it's a sub-step of an enclosing test, not a test in its
// own right, so it's excluded outright like the others rather than left to
// the zero-argument rule below.
const CONFIG_METHODS = new Set(["step", "use", "setTimeout", "slow", "extend", "configure", "info"]);

/** Does this `it.<method>`/`test.<method>`/`describe.<method>` member call
 * carry any evidence that the file organizes tests this way -- a real test,
 * or a describe/suite alias? Never a hook or config call. `roots` defaults to
 * `TEST_ROOTS` for isTestCall's use (a describe.only/describe.each modifier
 * is suite evidence, never a test in its own right); the suite gate in
 * isVitestFile passes `SUITE_ROOTS` so `describe.only(...)`/`describe.each`
 * still count there, matching pre-#679 behavior. One predicate either way, so
 * the two can no longer disagree about what a `test.<method>` call means
 * (#679 triage ruling). */
function isTestFrameworkMember(mem, roots = TEST_ROOTS) {
  return !!(mem && roots.has(mem.root) && !HOOK_METHODS.has(mem.method) && !CONFIG_METHODS.has(mem.method));
}

// skip/todo/only can't join the HOOK_METHODS/CONFIG_METHODS denylist above --
// `it.skip('title', fn)` is a real (skipped) test and must stay collected --
// but Playwright's `skip` also has a second, callback-free shape:
// `test.skip(cond, 'why')`, called in-body to conditionally skip the
// *enclosing* test. Two or more arguments and no callback is that shape, not
// a test definition (#774); a single argument stays ambiguous with a
// bodyless real test (`it.skip('title')`) and is left as a test, matching
// prior behavior.
const MODIFIER_METHODS = new Set(["skip", "todo", "only"]);

/** Does this CallExpression name a single test (`it`/`test`, incl. `.skip`)? */
function isTestCall(node) {
  const bare = calleeName(node);
  if (bare && TEST_ROOTS.has(bare)) return true;
  const mem = memberCallee(node);
  if (!isTestFrameworkMember(mem) || SUITE_ALIAS_METHODS.has(mem.method)) return false;
  // A zero-argument `test.<method>()` call is an in-body annotation
  // (`test.fixme()`, `test.slow()`), never a test definition -- `.fixme`
  // isn't in the denylist above because `test.fixme('title', fn)` is still a
  // real (skipped) test (#679 triage ruling).
  if (node.arguments.length === 0) return false;
  if (MODIFIER_METHODS.has(mem.method) && node.arguments.length > 1 && !testCallback(node)) return false;
  return true;
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

// A file is audited only when it identifies as one of the two runners in
// scope (#287: vitest and node:test) -- see SKILL.md § JS/TS reach for the
// rule and its remaining blind spot.
//
// Importing the runner is the signal that matters, and #685 added it. The
// original #287 guard was the assertion vocabulary alone, which costs exactly
// the file the gate most wants to catch: one whose every test is
// assertion-free has no assertion anywhere to be recognized by. The import
// does not reopen the #287 floodgate, because it is the stronger evidence of
// the two -- a homegrown harness imports its own `ok()`/`eq()`, never `vitest`
// or `node:test`.
//
// It does raise the cost of an assertion the vocabulary cannot see, from a
// skipped file to a build-blocking false finding. `assertBindings` below is
// what pays that cost.

/** Does the tree import from `module`? */
function importsFrom(tree, module) {
  let found = false;
  walk(tree, (n) => {
    if (n.type === "ImportDeclaration" && n.source.value === module) found = true;
  });
  return found;
}

function isVitestFile(tree) {
  if (importsFrom(tree, "vitest")) return true;
  let hasSuite = false;
  let hasExpect = false;
  walk(tree, (n) => {
    if (n.type !== "CallExpression") return;
    const bare = calleeName(n);
    const mem = memberCallee(n);
    // A hook or config call carries no evidence the file names tests this
    // way (#679 triage ruling) -- the shared predicate, not a raw root
    // match, is what keeps this gate and isTestCall from disagreeing.
    if ((bare && SUITE_ROOTS.has(bare)) || isTestFrameworkMember(mem, SUITE_ROOTS)) hasSuite = true;
    if (bare === "expect") hasExpect = true;
  });
  return hasSuite && hasExpect;
}

function isNodeTestFile(tree) {
  return importsFrom(tree, "node:test");
}

// --- assertion vocabulary --------------------------------------------------

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

const ASSERT_MODULES = new Set(["node:assert", "node:assert/strict", "assert", "assert/strict"]);

/**
 * The local names a file binds to node:assert, as `{ roots, matchers }`:
 *
 *   - `roots` are called as `<root>.<matcher>(...)`. `assert` is always one,
 *     with or without an import, because node's test context hangs the same
 *     API off `t.assert` and the trailing `assert.<matcher>` is what matches.
 *     A renamed default or namespace import (`import a from 'node:assert'`)
 *     joins it.
 *   - `matchers` are named imports called bare:
 *     `import { strictEqual } from 'node:assert'`.
 *
 * Both spellings are ordinary node:test style, and both were invisible while
 * the vocabulary was the literal `assert.*` alone. That was survivable when a
 * file had to show an `assert.*` call to be audited at all; once the runner
 * import admits the file (#685), an unrecognized assertion turns a correct
 * test into a build-blocking `assertion-free` finding.
 */
/** The name an import specifier reads from the module -- `x` in
 * `import { x as y }`, and in its string form `import { "x" as y }` -- or null
 * for a default or namespace import, which reads the module whole. */
function importedName(spec) {
  if (spec.type !== "ImportSpecifier") return null;
  return identifierName(spec.imported) || spec.imported.value;
}

function assertBindings(tree) {
  const roots = new Set(["assert"]);
  const matchers = new Set();
  walk(tree, (n) => {
    if (n.type !== "ImportDeclaration" || !ASSERT_MODULES.has(n.source.value)) return;
    for (const spec of n.specifiers) {
      // `strict` and `default` are namespace-like: they carry the whole
      // matcher set and are called as `<local>.<matcher>(...)`, not bare.
      const imported = importedName(spec);
      if (imported === null || imported === "strict" || imported === "default") {
        roots.add(spec.local.name);
      } else {
        matchers.add(spec.local.name);
      }
    }
  });
  return { roots, matchers };
}

// A file that binds nothing: `assert.*` still reads as an assertion, which is
// what the snippet-level selfchecks below parse without an import.
const NO_ASSERT_BINDINGS = { roots: new Set(["assert"]), matchers: new Set() };

/**
 * A `node:assert` call: `assert.equal(a, b)`, node's test-context spelling
 * `t.assert.equal(a, b)`, a named import called bare (`strictEqual(a, b)`), or
 * the bare `assert(x)` shorthand for `assert.ok(x)`. Returns { matcher, args }
 * or null.
 */
function assertCallInfo(node, bindings = NO_ASSERT_BINDINGS) {
  if (node.type !== "CallExpression") return null;
  const c = node.callee;
  const path = memberPath(c);
  // `assert.equal(...)`, node's test-context `t.assert.equal(...)`, and the
  // strict spelling of either (`assert.strict.equal(...)`), which slots a
  // `strict` segment between the binding and the matcher.
  if (path && path.length >= 2) {
    let root = path.length - 2;
    if (path[root] === "strict" && root > 0) root -= 1;
    if (bindings.roots.has(path[root])) {
      return { matcher: path[path.length - 1], args: node.arguments };
    }
  }
  const bare = identifierName(c);
  // `assert(x)` -- and the same shorthand through any other root binding --
  // is node:assert's spelling of `assert.ok(x)`.
  if (bare && bindings.roots.has(bare)) return { matcher: "ok", args: node.arguments };
  if (bare && bindings.matchers.has(bare)) return { matcher: bare, args: node.arguments };
  return null;
}

// Every assertion in a test body, `expect(...)` chains and `assert.*` calls
// alike, normalized to { isEq, actual, expected } — the shape both the
// assertion-free and tautology detectors need, regardless of vocabulary.
function assertionsIn(func, bindings) {
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
    const a = assertCallInfo(n, bindings);
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

// Every detector takes the same triple — the test CallExpression, the file
// source, and the file's node:assert bindings — mirroring audit.py's uniform
// `detector(func)`. Each pulls what it needs (callback, source) internally, so
// the scan loop stays a plain
// `for (smell, detector) if detector(call, source, bindings)`.

function isAssertionFree(call, source, bindings) {
  const cb = testCallback(call);
  // No callback (a bodyless `it`) is empty/skipped's concern, not this one.
  if (!cb) return false;
  return assertionsIn(cb, bindings).length === 0;
}

function isTautology(call, source, bindings) {
  const cb = testCallback(call);
  if (!cb) return false;
  for (const { isEq, actual, expected } of assertionsIn(cb, bindings)) {
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

function isAssertionCall(node, bindings) {
  return calleeName(node) === "expect" || !!asExpectAssertion(node) || !!assertCallInfo(node, bindings);
}

function isMockTheWorld(call, source, bindings) {
  const cb = testCallback(call);
  if (!cb) return false;
  let mockCalls = 0;
  let realCalls = 0;
  walk(cb.body, (n) => {
    if (n.type !== "CallExpression") return;
    if (isMockConstructCall(n)) {
      mockCalls += 1;
    } else if (!isAssertionCall(n, bindings)) {
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
function isInteractionOnly(call, source, bindings) {
  const cb = testCallback(call);
  if (!cb) return false;
  const assertions = assertionsIn(cb, bindings);
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
  return smellsIn(tree, source).map(([line, smell]) => [path, line, smell]);
}

/** `[line, smell]` for every DETECTORS hit in `tree` -- the one pipeline
 * scanFile and the selfcheck's own witness checks both run, so a witness
 * can't drift from what production actually does. */
function smellsIn(tree, source) {
  const bindings = assertBindings(tree);
  const found = [];
  for (const call of testCalls(tree)) {
    for (const [smell, detect] of DETECTORS) {
      if (detect(call, source, bindings)) found.push([lineOf(call), smell]);
    }
  }
  return found;
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
/** The smell names `smellsIn` finds for a snippet, in call order. */
function smellsOf(src) {
  return smellsIn(parseSource(src, "snippet.test.js"), src).map(([, smell]) => smell);
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
  // 0a. Playwright's bare conditional-skip form -- `test.skip(cond, 'why')`,
  // called in-body with no callback -- is a real test's own annotation, not a
  // test definition. Shape (condition+reason, no callback), not the `skip`
  // name, is what distinguishes it from `it.skip('title', fn)` (#774).
  assert(
    testCallCount(
      "test('t', ({ browserName }) => { test.skip(browserName === 'webkit', 'not supported'); expect(compute()).toBe(1); });",
    ) === 1,
    "in-body test.skip(cond, 'why') is not itself a test call -- only the enclosing test counts",
  );
  assert.deepEqual(
    smellsOf(
      "test('t', ({ browserName }) => { test.skip(browserName === 'webkit', 'not supported'); expect(compute()).toBe(1); });",
    ),
    [],
    "test.skip(cond, 'why') inside a real test -> no spurious empty/skipped finding",
  );
  assert(
    testCallCount("it.skip('x', () => { expect(a).toBe(b); })") === 1,
    "it.skip('title', fn) is still a real test call (unchanged)",
  );

  // 0b. suite aliases, config calls and bare in-body annotations are not test
  // calls (#679 triage ruling) -- one acceptance case per bullet in the
  // ruling comment.
  assert.deepEqual(
    smellsOf("test.describe('group', () => { test('works', () => { assert.equal(1, 1); }); });"),
    ["tautology"],
    "test.describe('group', () => test('works', () => assert.equal(1,1))) -> exactly one tautology, on the inner test",
  );
  assert.deepEqual(
    smellsOf("test.describe('x', () => {});"),
    [],
    "test.describe('x', () => {}) -> no findings",
  );
  assert(
    testCallCount("it.describe('group', () => { it('works', () => { expect(compute()).toBe(1); }); });") === 1,
    "it.describe is a suite too, not a test -- only the inner test call counts",
  );
  assert(testCallCount("test.suite('empty', () => {});") === 0, "an empty test.suite collects no test");
  assert.deepEqual(
    smellsOf(
      "test('t', async () => { await test.step('go', async () => { await page.click('#go'); }); expect(compute()).toBe(1); });",
    ),
    [],
    "test.step(...) inside a test -> no assertion-free test for the step",
  );
  assert.deepEqual(
    smellsOf("test('t', () => { test.use({ locale: 'en' }); expect(compute()).toBe(1); });"),
    [],
    "test.use({ locale: 'en' }) -> no empty/skipped test",
  );
  assert.deepEqual(
    smellsOf("test('t', () => { test.setTimeout(1000); expect(compute()).toBe(1); });"),
    [],
    "test.setTimeout(1000) -> no empty/skipped test",
  );
  assert.deepEqual(
    smellsOf("test('t', () => { test.fixme(); expect(compute()).toBe(1); });"),
    [],
    "in-body test.fixme() -> no finding",
  );
  assert(
    isEmptyOrSkipped(testCallFrom("test.fixme('t', () => {});")),
    "test.fixme('t', () => {}) -> still empty/skipped",
  );
  assert(
    !isVitestFile(parseSource("test.afterEach(() => { expect(a).toBe(b); });", "s.test.js")),
    "a file whose only test.<method> calls are hooks plus expect does not count as a suite via the gate",
  );
  // The gate's evidence predicate covers SUITE_ROOTS (describe/it/test), not
  // just TEST_ROOTS -- describe.only/describe.each are still suite evidence,
  // matching pre-#679 behavior; the widened denylist still excludes a
  // describe.<hook>/describe.<config> combination the same way (#679
  // verification pass).
  // No bare `it`/`test`/`describe` call anywhere in these two -- only the
  // modifier member call itself can supply suite evidence, isolating the
  // regression from a nested real test masking it.
  assert(
    isVitestFile(
      parseSource("describe.only('g', () => { hand('x', () => { expect(a).toBe(b); }); });", "s.test.js"),
    ),
    "describe.only(...) is still suite evidence via the gate",
  );
  assert(
    isVitestFile(
      parseSource("describe.each([1])('g %i', () => { hand('x', () => { expect(a).toBe(b); }); });", "s.test.js"),
    ),
    "describe.each(...) is still suite evidence via the gate",
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
  // #685 reverses this: an import of the runner is what identifies the
  // harness, so an all-hollow node:test file is audited rather than skipped.
  assert(
    isNodeTestFile(
      parseSource("import { test } from 'node:test';\ntest('x', () => { doStuff(a, b); });\n", "s.test.js"),
    ),
    "a node:test import identifies the file even with no assert.* call",
  );
  // The same for vitest: importing the runner is proof enough, so a file whose
  // every test is assertion-free is no longer skipped whole (#685).
  assert(
    isVitestFile(parseSource("import { it } from 'vitest';\nit('x', () => { compute(); });\n", "s.test.js")),
    "a vitest import identifies the file even with no expect call",
  );
  // The #287 guard is what the import signal replaces, and it must still
  // hold: a homegrown harness imports neither runner, so it stays skipped
  // whether or not it imports something of its own.
  const homegrown = parseSource(
    "import { ok, eq } from './harness.mjs';\ntest('x', () => { ok(compute()); });\n",
    "s.test.mjs",
  );
  assert(
    !isVitestFile(homegrown) && !isNodeTestFile(homegrown),
    "gate still skips a homegrown harness that imports neither runner",
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
    // These two files carry a real `expect`, so the assertion signal alone
    // admits them; the all-hollow case further down is the one that needs the
    // runner import to be seen at all (#685).
    const hollow = "it('hollow', () => { compute(); });\nit('real', () => { expect(a).toBe(1); });\n";
    mkdirSync(join(tmp, "fixtures"));
    writeFileSync(join(tmp, "fixtures", "specimen.test.js"), hollow);
    writeFileSync(join(tmp, "taut.test.js"), "it('x', () => { expect(x).toBe(x); });\n");
    // a deliberate specimen and a report-only smell: neither fails a build
    assert.deepEqual(gate(tmp)[0], [], "gate skips fixtures and non-gated smells");
    assert(scanPath(tmp).length > 0, "the report pass still sees both");

    // ...but the exemption is counted and reported. `fixtures` matches any
    // directory of that name at any depth, so without this line a repo could
    // park hollow tests under one and never see it (#685).
    assert.equal(gate(tmp)[1], 1, "gate counts what the fixtures exemption dropped");
    {
      const [code, err] = mainStderr(["node", "audit.mjs", "--gate", tmp]);
      assert.equal(code, 0, "a fixtures-only finding still passes the gate");
      assert(
        err.includes("1 assertion-free finding(s) suppressed under fixtures/"),
        `gate reports the suppressed count: ${err}`,
      );
    }

    writeFileSync(join(tmp, "hollow.test.js"), hollow);
    const [gated, suppressed] = gate(tmp);
    assert.equal(gated.length, 1, "gate catches the hollow test");
    assert(gated[0][0].endsWith("hollow.test.js"), "gate names the hollow test");
    assert.equal(suppressed, 1, "the fixtures specimen is still counted as suppressed");

    unlinkSync(join(tmp, "hollow.test.js"));
    assert.deepEqual(gate(tmp)[0], [], "gate is clean once the hollow test is gone");

    // Two ordinary node:test assertion spellings. The runner import admits
    // these files, so a vocabulary that did not recognize their assertions
    // would report every test in them as assertion-free and block the build --
    // the inverse of the bug #685 fixes.
    const ctxAssert = join(tmp, "ctx-assert.test.js");
    writeFileSync(
      ctxAssert,
      "import { test } from 'node:test';\ntest('x', (t) => { t.assert.strictEqual(compute(), 3); });\n",
    );
    const namedAssert = join(tmp, "named-assert.test.js");
    writeFileSync(
      namedAssert,
      "import { test } from 'node:test';\nimport { strictEqual } from 'node:assert';\n" +
        "test('x', () => { strictEqual(compute(), 3); });\n",
    );
    // node's strict mode reaches the same matchers through a `strict` segment,
    // as a member of the default export or as its own named import.
    const strictAssert = join(tmp, "strict-assert.test.js");
    writeFileSync(
      strictAssert,
      "import { test } from 'node:test';\nimport assert from 'node:assert';\n" +
        "test('x', () => { assert.strict.equal(compute(), 3); });\n",
    );
    const strictNamed = join(tmp, "strict-named.test.js");
    writeFileSync(
      strictNamed,
      "import { test } from 'node:test';\nimport { strict } from 'node:assert';\n" +
        "test('x', () => { strict.equal(compute(), 3); });\n",
    );
    // A root binding is callable as the `assert.ok` shorthand under any name,
    // and `default` is a spelling of that binding. (`importedName` also reads a
    // string-literal specifier; no input distinguishes that half, since such a
    // specifier otherwise falls through to `roots` and still reads as an
    // assertion, so nothing here claims to witness it.)
    const bareRoot = join(tmp, "bare-root.test.js");
    writeFileSync(
      bareRoot,
      "import { test } from 'node:test';\nimport a from 'node:assert';\n" +
        "test('x', () => { a(compute()); });\n",
    );
    const defaultSpec = join(tmp, "default-spec.test.js");
    writeFileSync(
      defaultSpec,
      "import { test } from 'node:test';\nimport { default as a } from 'node:assert';\n" +
        "test('x', () => { a.equal(compute(), 3); });\n",
    );
    assert.equal(
      quietMain(["node", "audit.mjs", "--gate", tmp]),
      0,
      "every ordinary node:assert spelling is a real assertion",
    );
    unlinkSync(ctxAssert);
    unlinkSync(namedAssert);
    unlinkSync(strictAssert);
    unlinkSync(strictNamed);
    unlinkSync(bareRoot);
    unlinkSync(defaultSpec);


    // The file the gate most wants to catch: every test in it is hollow, so
    // there is no `expect` anywhere to identify it by. The runner import is
    // what identifies it now (#685).
    const allHollow = join(tmp, "all-hollow.test.js");
    writeFileSync(allHollow, "import { it } from 'vitest';\nit('x', () => { compute(); });\n");
    assert.equal(quietMain(["node", "audit.mjs", "--gate", tmp]), 1, "an all-hollow vitest file fails the gate");
    unlinkSync(allHollow);

    // A root that does not exist was not checked, so the gate must not report
    // success: EXIT_UNABLE, distinct from both 0 (clean) and 1 (hollow tests
    // found), so a typo in a repo's wiring reads differently from a real
    // finding (#685).
    const missing = join(tmp, "no-such-dir");
    {
      // Each guard is witnessed by its own message: `accessSync` also rejects a
      // missing path, so a status-only assertion would leave the existence
      // branch passing with its constraint stripped.
      const [code, err] = mainStderr(["node", "audit.mjs", "--gate", missing]);
      assert.equal(code, EXIT_UNABLE, "gate refuses a missing root");
      assert(err.includes("no such path"), `gate names a missing root: ${err}`);
    }
    assert.equal(quietMain(["node", "audit.mjs", missing]), EXIT_UNABLE, "report refuses a missing root");
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }

  // A root that exists but cannot be read was not checked either -- the same
  // lie as a missing root, reached by EACCES instead of ENOENT (#685). Its own
  // root, never the shared one above: a hollow fixture parked under a root that
  // later assertions gate on is what makes those assertions pass.
  //
  // Skipped for uid 0, which is granted access whatever the mode, so the tree
  // would scan and the gate would find the fixture.
  if (!(process.getuid && process.getuid() === 0)) {
    const denied = mkdtempSync(join(tmpdir(), "test-audit-eacces-"));
    try {
      writeFileSync(join(denied, "hollow.test.js"), "it('x', () => { compute(); });\nit('y', () => { expect(a).toBe(1); });\n");
      // Readable but not listable, then not readable at all: both leave the
      // walk with nothing, so both must refuse rather than report clean.
      for (const mode of [0o444, 0o000]) {
        chmodSync(denied, mode);
        const [code, err] = mainStderr(["node", "audit.mjs", "--gate", denied]);
        chmodSync(denied, 0o755);
        assert.equal(code, EXIT_UNABLE, `gate refuses a root it cannot read (mode ${mode.toString(8)})`);
        assert(err.includes("cannot read"), `gate says it could not read the root: ${err}`);
      }
    } finally {
      chmodSync(denied, 0o755);
      rmSync(denied, { recursive: true, force: true });
    }
  }

  process.stdout.write("ok\n");
}

// --- gate mode -------------------------------------------------------------

// The one smell a build gates on -- the Python side's GATE_SMELL, same
// reasoning: the other four still run and still fail when the behavior
// breaks, while an assertion-free test cannot fail at all.
const GATE_SMELL = "assertion-free test";

// Exit status contract: 0 clean, 1 hollow tests found, 2 unable to check --
// the status the bootstrap failure above already uses. Only gate mode ever
// returns 1 -- a report never fails a build -- but 0 and 2 mean the same in
// both. A root that does not exist gets 2 and never 0: a gate that reports
// success while it scanned nothing is a lie, and it fails silently and
// permanently once wired into a repo's build (#685). Mirrors audit.py.
const EXIT_UNABLE = 2;

/** Does `path` lie under a `fixtures/` directory? A fixture is a deliberate
 * specimen of the smell, so the gate never counts one; the report still does. */
function underFixtures(path) {
  return path.split(/[\\/]/).includes("fixtures");
}

/** `[findings, suppressed]` -- the `GATE_SMELL` findings that fail a build,
 * and how many the fixtures exemption dropped.
 *
 * The count is returned, and reported by `main`, because `underFixtures`
 * matches a `fixtures` segment at any depth: without it a repo could park
 * hollow tests under any directory it named `fixtures` and never see that the
 * gate had stopped looking at them (#685). Mirrors audit.py. */
function gate(root) {
  const gated = scanPath(root).filter(([, , smell]) => smell === GATE_SMELL);
  const findings = gated.filter(([path]) => !underFixtures(path));
  return [findings, gated.length - findings.length];
}

// --- main ------------------------------------------------------------------

// A function returning its exit status rather than calling process.exit, so
// the selfcheck can assert on that status -- mirrors audit.py's `main(argv)`.
function main(argv) {
  const arg = argv[2];
  if (arg === "--selfcheck") {
    selfcheck();
    return 0;
  }
  const gateMode = arg === "--gate";
  const root = (gateMode ? argv[3] : arg) || ".";
  // Refuse a root that does not exist before scanning it. Walking a missing
  // directory finds nothing, and "nothing" is indistinguishable from a clean
  // tree -- so a typo in a repo's wiring would make its gate permanently
  // green (#685).
  if (!existsSync(root)) {
    process.stderr.write(`test-audit: no such path: ${root} -- nothing was scanned.\n`);
    return EXIT_UNABLE;
  }
  // The same lie by a different errno: a root that exists but cannot be read
  // walks to zero files, which is indistinguishable from a clean tree. Only
  // the root is checked here -- an unreadable directory deeper in the tree is
  // still swallowed by `collect`, which is a wider fix than #685 asked for.
  try {
    // A directory needs X_OK as well: R_OK alone lists it, but opening the
    // files inside it still fails, so the walk yields nothing.
    const needed = statSync(root).isDirectory() ? constants.R_OK | constants.X_OK : constants.R_OK;
    accessSync(root, needed);
  } catch {
    process.stderr.write(`test-audit: cannot read ${root} -- nothing was scanned.\n`);
    return EXIT_UNABLE;
  }
  if (gateMode) {
    const [findings, suppressed] = gate(root);
    for (const [path, line, smell] of findings) process.stdout.write(`${path}:${line}: ${smell}\n`);
    if (suppressed > 0) {
      process.stderr.write(`test-audit: ${suppressed} assertion-free finding(s) suppressed under fixtures/.\n`);
    }
    if (findings.length > 0) {
      process.stderr.write(
        `test-audit: ${findings.length} assertion-free test(s) -- a test that cannot fail proves nothing.\n`,
      );
      return 1;
    }
    return 0;
  }
  const findings = scanPath(root);
  for (const [path, line, smell] of findings) process.stdout.write(`${path}:${line}: ${smell}\n`);
  if (findings.length === 0) process.stderr.write("no mechanical smells found\n");
  return 0;
}

/** `[exitStatus, stderrText]` -- `main` with its report swallowed, so a
 * passing suite prints only `ok`. The gate reports its suppressed-fixtures
 * count on stderr, so the selfcheck reads it there. Mirrors audit.py's
 * `_main_stderr`. */
function mainStderr(argv) {
  const out = process.stdout.write;
  const errWrite = process.stderr.write;
  let captured = "";
  process.stdout.write = () => true;
  process.stderr.write = (chunk) => {
    captured += chunk;
    return true;
  };
  try {
    return [main(argv), captured];
  } finally {
    process.stdout.write = out;
    process.stderr.write = errWrite;
  }
}

function quietMain(argv) {
  return mainStderr(argv)[0];
}

process.exit(main(process.argv));
