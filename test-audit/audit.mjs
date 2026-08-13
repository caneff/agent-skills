#!/usr/bin/env node
/**
 * Pass one of test-audit for JS/TS: the node sibling of audit.py.
 *
 * Scans vitest-style test files on a real @babel/parser AST and emits the same
 * `file:line: <smell>` candidates audit.py does for pytest. This script never
 * classifies — it only surfaces candidates for the judgment pass (SKILL.md).
 *
 * Walking skeleton (#301): three shallow smells on vitest only —
 *   1. assertion-free   — the test body has no `expect(...)` assertion.
 *   2. tautology        — `expect(x).toBe(x)` (same expression both sides).
 *   3. empty/skipped    — empty body, or `.skip`/`.todo`, or a bodyless `it`.
 *
 * node:test recognition + `assert.*` (#302) and the two mock smells (#303)
 * land in follow-ups; audit.py keeps the pytest path untouched.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, basename, extname } from "node:path";
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

/** The bare callee name for an Identifier call, else null. */
function calleeName(node) {
  if (node.type !== "CallExpression") return null;
  const c = node.callee;
  if (c.type === "Identifier") return c.name;
  return null;
}

/** The `object.property` root+method for a member-call (`it.skip`), else null. */
function memberCallee(node) {
  if (node.type !== "CallExpression") return null;
  const c = node.callee;
  if (c.type === "MemberExpression" && c.object.type === "Identifier" && c.property.type === "Identifier") {
    return { root: c.object.name, method: c.property.name };
  }
  return null;
}

const TEST_ROOTS = new Set(["it", "test"]);
const SUITE_ROOTS = new Set(["describe", "it", "test"]);

/** Does this CallExpression name a single test (`it`/`test`, incl. `.skip`)? */
function isTestCall(node) {
  const bare = calleeName(node);
  if (bare && TEST_ROOTS.has(bare)) return true;
  const mem = memberCallee(node);
  return !!(mem && TEST_ROOTS.has(mem.root));
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

// --- assertion vocabulary --------------------------------------------------

const EQ_MATCHERS = new Set(["toBe", "toEqual", "toStrictEqual"]);

/**
 * An `expect(...).matcher(...)` assertion is a CallExpression whose callee is a
 * MemberExpression rooted (through any chained `.not`/`.resolves`/...) at an
 * `expect(...)` call. Returns { expectCall, matcher, matcherCall } or null.
 */
function asExpectAssertion(node) {
  if (node.type !== "CallExpression" || node.callee.type !== "MemberExpression") return null;
  const matcher = node.callee.property.type === "Identifier" ? node.callee.property.name : null;
  let obj = node.callee.object;
  while (obj && obj.type === "MemberExpression") obj = obj.object; // walk past .not/.resolves
  if (obj && obj.type === "CallExpression" && calleeName(obj) === "expect") {
    return { expectCall: obj, matcher, matcherCall: node };
  }
  return null;
}

function expectAssertions(func) {
  const out = [];
  walk(func.body, (n) => {
    const a = asExpectAssertion(n);
    if (a) out.push(a);
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
  return expectAssertions(cb).length === 0;
}

function isTautology(call, source) {
  const cb = testCallback(call);
  if (!cb) return false;
  for (const { expectCall, matcher, matcherCall } of expectAssertions(cb)) {
    if (!EQ_MATCHERS.has(matcher)) continue;
    const actual = expectCall.arguments[0];
    const expected = matcherCall.arguments[0];
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

const DETECTORS = [
  ["assertion-free test", isAssertionFree],
  ["tautology", isTautology],
  ["empty/skipped test", isEmptyOrSkipped],
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
  if (!isVitestFile(tree)) return [];
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
const PRUNE_DIRS = new Set(["node_modules", "dist", "build", ".git", "worktrees", ".venv"]);

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

function selfcheck() {
  // 1. assertion-free
  assert(isAssertionFree(testCallFrom("it('x', () => { const y = compute(); })")), "assertion-free positive");
  assert(!isAssertionFree(testCallFrom("it('x', () => { expect(compute()).toBe(5); })")), "assertion-free negative");

  // 2. tautology
  assert(tautologyOf("it('x', () => { expect(x).toBe(x); })"), "tautology positive");
  assert(!tautologyOf("it('x', () => { expect(x).toBe(5); })"), "tautology negative");

  // 3. empty/skipped
  assert(isEmptyOrSkipped(testCallFrom("it('x', () => {})")), "empty body positive");
  assert(isEmptyOrSkipped(testCallFrom("it.skip('x', () => { expect(a).toBe(b); })")), "skip positive");
  assert(!isEmptyOrSkipped(testCallFrom("it('x', () => { expect(a).toBe(b); })")), "empty/skipped negative");

  // recognize-or-skip gate
  assert(isVitestFile(parseSource("it('x', () => { expect(a).toBe(b); })", "s.test.js")), "gate recognizes vitest");
  assert(
    !isVitestFile(parseSource("harness('x', () => { check(a, b); })", "s.test.js")),
    "gate skips homegrown harness",
  );

  process.stdout.write("ok\n");
}

// --- main ------------------------------------------------------------------

const arg = process.argv[2];
if (arg === "--selfcheck") {
  selfcheck();
} else {
  const findings = scanPath(arg || ".");
  for (const [path, line, smell] of findings) process.stdout.write(`${path}:${line}: ${smell}\n`);
  if (findings.length === 0) process.stderr.write("no mechanical smells found\n");
}
