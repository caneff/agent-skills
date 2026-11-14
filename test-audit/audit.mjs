#!/usr/bin/env node
/**
 * Pass one of test-audit for JS/TS: the node sibling of audit.py.
 *
 * Scans vitest-style test files on a real @babel/parser AST and emits the same
 * `file:line: <smell>` candidates audit.py does for pytest. This script never
 * classifies — it only surfaces candidates for the judgment pass (SKILL.md).
 *
 * Seven smells; the first five run on vitest and node:test alike —
 *   1. assertion-free   — the test body has no `expect(...)`/`assert.*` call.
 *   2. tautology        — `expect(x).toBe(x)` / `assert.equal(x, x)`.
 *   3. empty/skipped    — empty body, or `.skip`/`.todo`, or a bodyless `it`.
 *   4. mock-the-world   — mock constructs exceed a ceiling, little real logic.
 *   5. interaction-only — every assertion only checks that a spy was called.
 *   6. broad exception  — `toThrow()` / `toThrowError()` with no argument
 *                         passes on the wrong error. Vitest `expect` only.
 *   7. duplicate title  — two tests in one describe with the same literal
 *                         title (the "lost test (duplicate name)" smell of
 *                         docs/research/2026-10-08-test-smell-gaps.md). Vitest
 *                         files only.
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
  realpathSync,
} from "node:fs";
import { join, basename, extname } from "node:path";
import { fileURLToPath } from "node:url";

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

// `skip` can't simply join the HOOK_METHODS/CONFIG_METHODS denylist above --
// `it.skip('title', fn)` is a real (skipped) test and must stay collected --
// but Playwright's `skip` also has a second, callback-free shape, used
// in-body to conditionally skip the *enclosing* test: `test.skip(cond,
// 'why')`, `cond` a boolean or a fixture-reading predicate function
// (`test.skip(({ browserName }) => browserName === 'webkit', 'why')`). Only
// `skip` has this second shape -- `todo`/`only` don't take a condition, so
// they're left out rather than inheriting a narrowing they don't need.
//
// The two shapes put a string in different positions: a real test's last
// argument is always its callback, inline or a named reference
// (`it.skip('t', fn)`, `it.skip(computedTitle, sharedFn)`); the bare
// annotation's last argument is always its trailing reason string, whatever
// the condition looks like (`test.skip(cond, 'why')`,
// `test.skip(fnCond, 'why')`) (#774). Checking the *last* argument, not the
// first, is what keeps a computed/non-literal title (`it.skip(c.name, fn)`)
// from being mistaken for the annotation shape. A single argument
// (`test.skip(cond)`, `it.skip('title')`) stays ambiguous either way and is
// left as a test, matching prior behavior.
const MODIFIER_METHODS = new Set(["skip"]);

function isReasonArg(node) {
  return !!node && (node.type === "StringLiteral" || node.type === "TemplateLiteral");
}

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
  if (MODIFIER_METHODS.has(mem.method) && node.arguments.length > 1 && isReasonArg(node.arguments[node.arguments.length - 1]))
    return false;
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
// what the snippet tests in audit.test.mjs parse without an import.
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
        node: n,
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
        node: n,
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

const STUB_SMELL = "stub asserted called";
const STUB_MATCHERS = new Set([
  "mockReturnValue",
  "mockReturnValueOnce",
  "mockResolvedValue",
  "mockResolvedValueOnce",
  "mockRejectedValue",
  "mockRejectedValueOnce",
  "mockImplementation",
  "mockImplementationOnce",
]);

/** What a chain like `vi.fn().mockReturnValue(1)`, `vi.fn(impl)`,
 * `vi.mocked(get).mockResolvedValue(1)`, `get.mockResolvedValue(1)` or
 * `vi.spyOn(obj, "get").mockReturnValue(1)` stubs, as the source texts
 * `expect(...)` would name it by: `[]` for an anonymous `vi.fn()`, `["get"]`
 * for `vi.mocked(get)` or a mock already named, `["obj.get"]` for a spy.
 * `null` when the chain supplies no input. */
function stubNames(chain, source) {
  const text = (x) => source.slice(x.start, x.end);
  let stubs = false;
  let n = chain;
  while (n.type === "CallExpression" && n.callee.type === "MemberExpression") {
    if (STUB_MATCHERS.has(identifierName(n.callee.property))) stubs = true;
    const path = memberPath(n.callee);
    const vi = path && path.length === 2 && path[0] === "vi" ? path[1] : null;
    if (vi === "spyOn" && n.arguments.length === 2) {
      const [target, name] = n.arguments;
      return stubs && name.type === "StringLiteral" ? [`${text(target)}.${name.value}`] : null;
    }
    if (vi === "mocked" && n.arguments.length === 1) return stubs ? [text(n.arguments[0])] : null;
    if (vi === "fn") return stubs || n.arguments.length > 0 ? [] : null;
    n = n.callee.object;
  }
  return stubs ? [text(n)] : null;
}

/** A vitest mock that supplies input (the `mockReturnValue` / `mockResolvedValue`
 * / `mockRejectedValue` / `mockImplementation` families, `vi.fn(impl)`) and is
 * also checked with a `toHaveBeenCalled*` matcher. `isInteractionOnly` misses
 * this mixed form (SKILL.md: stub asserted called). */
function hasCalledStub(call, source, bindings) {
  const cb = testCallback(call);
  if (!cb) return false;
  const stubbed = new Set();
  walk(cb.body, (n) => {
    // `const get = vi.fn().mockReturnValue(1)`: the declared name is the stub too.
    // `let g; g = vi.fn(...)` names the stub as well.
    const bound =
      n.type === "VariableDeclarator" && n.id.type === "Identifier" && n.init
        ? [n.id.name, n.init]
        : n.type === "AssignmentExpression" && n.left.type === "Identifier"
          ? [n.left.name, n.right]
          : null;
    const names = bound ? stubNames(bound[1], source) : n.type === "ExpressionStatement" ? stubNames(n.expression, source) : null;
    if (!names) return;
    for (const name of names) stubbed.add(name);
    if (bound) stubbed.add(bound[0]);
  });
  return assertionsIn(cb, bindings).some(
    (a) =>
      a.kind === "expect" &&
      INTERACTION_MATCHERS.has(a.matcher) &&
      a.actual &&
      stubbed.has(source.slice(a.actual.start, a.actual.end)),
  );
}

const VACUOUS_SMELL = "vacuous loop assertion";

// Calls that hand back their argument's contents, so iterating
// `Object.keys(result)` walks `result`. Any other call is itself an output.
const PASS_THROUGH_ROOTS = new Set(["Object", "Array"]);
const VIEW_METHODS = new Set(["entries", "values", "keys"]);

/** Does iterating `node` walk something the code under test returned: a call's
 * result, or a local name declared from one (`fromCall`)? A literal collection
 * or a name the test never declares (a module constant) is a fixed input and
 * is never empty by accident. */
const LITERAL_TYPES = new Set(["ArrayExpression", "ObjectExpression", "StringLiteral", "NumericLiteral", "BooleanLiteral", "NullLiteral"]);

/** A call whose result is the code under test's: not a method on a literal
 * (`[1, 2].map(f)`) and not a call whose every argument is a literal
 * (`Object.keys({ a: 1 })`). */
function isOutputCall(call) {
  if (call.callee.type === "MemberExpression" && LITERAL_TYPES.has(call.callee.object.type)) return false;
  return !(call.arguments.length > 0 && call.arguments.every((a) => LITERAL_TYPES.has(a.type)));
}

function isOutputIterable(node, fromCall) {
  switch (node.type) {
    case "Identifier":
      return fromCall.has(node.name);
    case "MemberExpression":
    case "OptionalMemberExpression":
      return isOutputIterable(node.object, fromCall);
    case "AwaitExpression":
      return true;
    case "ChainExpression":
    case "TSNonNullExpression":
      return isOutputIterable(node.expression, fromCall);
    case "CallExpression":
    case "OptionalCallExpression": {
      const c = node.callee;
      if (c.type === "MemberExpression" && PASS_THROUGH_ROOTS.has(identifierName(c.object))) {
        return node.arguments.some((a) => isOutputIterable(a, fromCall));
      }
      if (c.type === "MemberExpression" && VIEW_METHODS.has(identifierName(c.property))) {
        return isOutputIterable(c.object, fromCall);
      }
      return isOutputCall(node);
    }
    default:
      return false;
  }
}

/** Every assertion sits in a `for...of`, `for...in` or `.forEach` over what
 * the code under test returned, so an empty result runs none of them and the
 * test passes. An assertion outside such a loop, a length or non-empty check
 * included, clears it. */
function isVacuousLoop(call, source, bindings) {
  const cb = testCallback(call);
  if (!cb) return false;
  const assertions = assertionsIn(cb, bindings);
  if (assertions.length === 0) return false;
  // `expect.hasAssertions()` / `expect.assertions(n)` fail an empty loop.
  let counted = false;
  walk(cb.body, (n) => {
    const path = n.type === "CallExpression" ? memberPath(n.callee) : null;
    if (path && path.length === 2 && path[0] === "expect" && (path[1] === "hasAssertions" || path[1] === "assertions")) counted = true;
  });
  if (counted) return false;
  const fromCall = new Set();
  walk(cb.body, (n) => {
    if (n.type !== "VariableDeclarator" || n.id.type !== "Identifier" || !n.init) return;
    let hasCall = false;
    walk(n.init, (m) => {
      if ((m.type === "CallExpression" && isOutputCall(m)) || m.type === "AwaitExpression") hasCall = true;
    });
    if (hasCall) fromCall.add(n.id.name);
  });
  const loops = [];
  walk(cb.body, (n) => {
    if ((n.type === "ForOfStatement" || n.type === "ForInStatement") && isOutputIterable(n.right, fromCall)) {
      loops.push(n.body);
    } else if (
      n.type === "CallExpression" &&
      n.callee.type === "MemberExpression" &&
      identifierName(n.callee.property) === "forEach" &&
      n.arguments.length > 0 &&
      isOutputIterable(n.callee.object, fromCall)
    ) {
      loops.push(n.arguments[0]);
    }
  });
  return assertions.every((a) => loops.some((l) => a.node.start >= l.start && a.node.end <= l.end));
}

const PRIVATE_SMELL = "private-API access";
const TS_SUPPRESSION = /@ts-(ignore|expect-error)\b/;

const isMember = (n) => n.type === "MemberExpression" || n.type === "OptionalMemberExpression";

/** Is `member` the matcher half of an `expect(...).toX` chain? A
 * `@ts-expect-error` above `expect(() => f(1)).toThrow()` silences a type
 * error in the argument, not a member access. */
function isExpectChain(member) {
  let obj = member.object;
  while (obj && isMember(obj)) obj = obj.object;
  return !!obj && obj.type === "CallExpression" && calleeName(obj) === "expect";
}

/** `[line, smell]` for each test that reaches past the public surface of what
 * it tests: `(x as any).name`, `x["_name"]`, or a member access on the line
 * under a `@ts-ignore` / `@ts-expect-error`. It reaches into what a caller
 * cannot see, so an internal rename turns the test red though no behavior
 * changed. Candidate only: the judgment pass tells a deliberate type test from
 * a private read. */
function privateAccess(tree) {
  const found = [];
  for (const call of testCalls(tree)) {
    const cb = testCallback(call);
    if (!cb) continue;
    const suppressed = (tree.comments || [])
      .filter((c) => TS_SUPPRESSION.test(c.value) && c.start >= cb.start && c.end <= cb.end)
      .map((c) => c.loc.end.line + 1);
    // A function passed to `expect` is the call whose throw is tested; a
    // `@ts-expect-error` above it silences a wrong argument, not a member read.
    const tested = [];
    walk(cb.body, (n) => {
      const arg = n.type === "CallExpression" && calleeName(n) === "expect" ? n.arguments[0] : null;
      if (arg && (arg.type === "ArrowFunctionExpression" || arg.type === "FunctionExpression")) tested.push(arg);
    });
    let hit = false;
    walk(cb.body, (n) => {
      if (!isMember(n)) return;
      const obj = n.object;
      if (
        (obj.type === "TSAsExpression" || obj.type === "TSTypeAssertion") &&
        obj.typeAnnotation.type === "TSAnyKeyword"
      ) {
        hit = true;
      } else if (
        n.computed &&
        n.property.type === "StringLiteral" &&
        /^_(?!_.*__$)/.test(n.property.value) &&
        obj.type !== "ThisExpression"
      ) {
        hit = true;
      } else if (suppressed.includes(n.loc.start.line) && !isExpectChain(n) && !tested.some((f) => n.start >= f.start && n.end <= f.end)) {
        hit = true;
      }
    });
    if (hit) found.push([lineOf(call), PRIVATE_SMELL]);
  }
  return found;
}

const BROAD_THROW_MATCHERS = new Set(["toThrow", "toThrowError"]);

/** Is `matcherCall` negated, as in `expect(f).not.toThrow()`? */
function isNegated(matcherCall) {
  let obj = matcherCall.callee.object;
  while (obj && obj.type === "MemberExpression") {
    if (identifierName(obj.property) === "not") return true;
    obj = obj.object;
  }
  return false;
}

/** A `toThrow()` / `toThrowError()` with no argument: it passes on any error,
 * the wrong one included. `.not.toThrow()` asserts the opposite and is not
 * this smell. */
function isBroadThrow(call) {
  const cb = testCallback(call);
  if (!cb) return false;
  let found = false;
  walk(cb.body, (n) => {
    const e = asExpectAssertion(n);
    if (e && BROAD_THROW_MATCHERS.has(e.matcher) && e.matcherCall.arguments.length === 0 && !isNegated(e.matcherCall)) {
      found = true;
    }
  });
  return found;
}

const DETECTORS = [
  ["assertion-free test", isAssertionFree],
  ["tautology", isTautology],
  ["empty/skipped test", isEmptyOrSkipped],
  ["mock-the-world", isMockTheWorld],
  ["interaction-only assertion", isInteractionOnly],
  ["broad exception expectation", isBroadThrow],
  [STUB_SMELL, hasCalledStub],
  [VACUOUS_SMELL, isVacuousLoop],
];

const LOST_DUPLICATE = "lost test (duplicate name)";

/** A `describe`/`suite` call, including a modifier (`describe.only`) and the
 * Playwright alias `test.describe`; not `describe.each(...)(...)`, whose callee
 * is itself a call. */
function isDescribeCall(node) {
  if (node.type !== "CallExpression") return false;
  const bare = calleeName(node);
  if (bare) return SUITE_ALIAS_METHODS.has(bare);
  const mem = memberCallee(node);
  return !!mem && (SUITE_ALIAS_METHODS.has(mem.root) || (TEST_ROOTS.has(mem.root) && SUITE_ALIAS_METHODS.has(mem.method)));
}

/** The title when it is a literal: a string, or a template with no
 * substitution. Else null -- a computed title is not a repeat of anything. */
function literalTitle(call) {
  const arg = call.arguments[0];
  if (!arg) return null;
  if (arg.type === "StringLiteral") return arg.value;
  if (arg.type === "TemplateLiteral" && arg.expressions.length === 0) return arg.quasis[0].value.cooked;
  return null;
}

/** `[line, smell]` for every test that repeats an earlier test's literal title
 * among the same describe's direct statements. Reported at the repeat. */
function duplicateTitles(tree) {
  const found = [];
  walk(tree, (n) => {
    if (!isDescribeCall(n)) return;
    const cb = testCallback(n);
    if (!cb || cb.body.type !== "BlockStatement") return;
    const seen = new Set();
    for (const stmt of cb.body.body) {
      if (stmt.type !== "ExpressionStatement" || !isTestCall(stmt.expression)) continue;
      // `it.todo('a')` has no body for a later definition to replace.
      if (!testCallback(stmt.expression)) continue;
      const title = literalTitle(stmt.expression);
      if (title === null) continue;
      if (seen.has(title)) found.push([lineOf(stmt.expression), LOST_DUPLICATE]);
      seen.add(title);
    }
  });
  return found;
}

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

/** `[line, smell]` for every DETECTORS hit in `tree`, plus the checks that read
 * the whole file (duplicate titles; private-API access, which needs the
 * comments) -- the one pipeline
 * scanFile and audit.test.mjs's witness checks both run, so a witness
 * can't drift from what production actually does. */
function smellsIn(tree, source) {
  const bindings = assertBindings(tree);
  const found = [];
  for (const call of testCalls(tree)) {
    for (const [smell, detect] of DETECTORS) {
      if (detect(call, source, bindings)) found.push([lineOf(call), smell]);
    }
  }
  if (isVitestFile(tree)) found.push(...duplicateTitles(tree));
  found.push(...privateAccess(tree));
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

// --- gate mode -------------------------------------------------------------

// The smells a build gates on -- the Python side's GATE_SMELLS, each with the
// label its fixtures-suppression count is reported under. SKILL.md § Gate mode
// says why these two and no other.
const GATE_SMELLS = new Map([
  ["assertion-free test", "assertion-free"],
  [LOST_DUPLICATE, "duplicate-name"],
]);

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

/** `[findings, suppressed]` -- the `GATE_SMELLS` findings that fail a build,
 * and how many the fixtures exemption dropped, per `GATE_SMELLS` label.
 *
 * The count is returned, and reported by `main`, because `underFixtures`
 * matches a `fixtures` segment at any depth: without it a repo could park
 * hollow tests under any directory it named `fixtures` and never see that the
 * gate had stopped looking at them (#685). Mirrors audit.py. */
function gate(root) {
  const gated = scanPath(root).filter(([, , smell]) => GATE_SMELLS.has(smell));
  const findings = gated.filter(([path]) => !underFixtures(path));
  const suppressed = {};
  for (const [path, , smell] of gated) {
    if (underFixtures(path)) suppressed[GATE_SMELLS.get(smell)] = (suppressed[GATE_SMELLS.get(smell)] ?? 0) + 1;
  }
  return [findings, suppressed];
}

// --- main ------------------------------------------------------------------

// A function returning its exit status rather than calling process.exit, so
// audit.test.mjs can assert on that status -- mirrors audit.py's `main(argv)`.
function main(argv) {
  const arg = argv[2];
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
    for (const [label, count] of Object.entries(suppressed)) {
      process.stderr.write(`test-audit: ${count} ${label} finding(s) suppressed under fixtures/.\n`);
    }
    if (findings.length > 0) {
      process.stderr.write(
        `test-audit: ${findings.length} test(s) that cannot fail -- a test that cannot fail proves nothing.\n`,
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

// Importing this file (audit.test.mjs does) must not scan or exit; only
// `node audit.mjs` runs the CLI.
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main(process.argv));
}

export {
  EXIT_UNABLE,
  LOST_DUPLICATE,
  PRIVATE_SMELL,
  STUB_SMELL,
  VACUOUS_SMELL,
  gate,
  isAssertionFree,
  isBroadThrow,
  isEmptyOrSkipped,
  isInteractionOnly,
  isMockTheWorld,
  isNodeTestFile,
  isTautology,
  isVitestFile,
  main,
  parseSource,
  scanPath,
  smellsIn,
  testCalls,
};
