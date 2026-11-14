// Tests for audit.mjs, the JS sibling of audit.py. One node:test case per
// detector group, so a failure names the group instead of stopping the whole
// check at its first bad assertion (#1743). These were audit.mjs's `--selfcheck`.
import { test } from "node:test";
import assert from "node:assert";
import { chmodSync, mkdirSync, mkdtempSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { tmpdir } from "node:os";
import {
  EXIT_UNABLE,
  LOST_DUPLICATE,
  PRIVATE_SMELL,
  STUB_SMELL,
  SUITE_ROOTS,
  TEST_ROOTS,
  VACUOUS_SMELL,
  assertionsIn,
  gate,
  importedName,
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
  walk,
} from "./audit.mjs";

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

test('test-call collection: modifiers are tests, lifecycle hooks are not (#677)', () => {
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
});

test("Playwright's in-body test.skip(cond, 'why') is an annotation, not a test call (#774)", () => {
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
  // The condition can itself be a fixture-reading callback -- a function in
  // the first-argument (condition) position is still the annotation shape,
  // not a test, because the title always comes first in a real test.
  assert(
    testCallCount(
      "test('t', ({ browserName }) => { test.skip(({ browserName }) => browserName === 'webkit', 'not supported'); expect(compute()).toBe(1); });",
    ) === 1,
    "in-body test.skip(callback-condition, 'why') is not itself a test call either",
  );
  assert.deepEqual(
    smellsOf(
      "test('t', ({ browserName }) => { test.skip(({ browserName }) => browserName === 'webkit', 'not supported'); expect(compute()).toBe(1); });",
    ),
    [],
    "test.skip(callback-condition, 'why') inside a real test -> no spurious finding",
  );
  // A real skipped test's callback need not be inline, and its title need
  // not be a literal -- the callback in the last-argument position is what
  // makes it a test, not the title's own shape.
  assert(
    testCallCount("function body() { expect(a).toBe(b); } it.skip('x', body);") === 1,
    "it.skip('title', <named callback>) is still a real test call",
  );
  assert(
    testCallCount("for (const c of cases) { it.skip(c.name, () => { expect(a).toBe(b); }); }") === 1,
    "it.skip(<computed title>, fn) is still a real test call",
  );
});

test('suite aliases, config calls and in-body annotations are not test calls (#679)', () => {
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
});

test('assertion-free', () => {
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
});

test('tautology', () => {
  // 2. tautology
  assert(tautologyOf("it('x', () => { expect(x).toBe(x); })"), "tautology positive");
  assert(!tautologyOf("it('x', () => { expect(x).toBe(5); })"), "tautology negative");
  assert(tautologyOf("test('x', () => { assert.equal(x, x); })"), "tautology positive (node:test)");
  assert(!tautologyOf("test('x', () => { assert.equal(x, 5); })"), "tautology negative (node:test)");
});

test('empty/skipped', () => {
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
});

test('recognize-or-skip gate: runner imports identify a test file (#685)', () => {
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
});

test('mock-the-world', () => {
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
});

test('interaction-only assertion', () => {
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
});

test('broad exception expectation', () => {
  // 6. broad exception expectation: `toThrow()` / `toThrowError()` with no
  // argument pass on any error, the wrong one included.
  const broad = (src) => isBroadThrow(testCallFrom(src));
  assert(broad("it('x', () => { expect(() => f()).toThrow(); })"), "toThrow() positive");
  assert(broad("it('x', () => { expect(() => f()).toThrowError(); })"), "toThrowError() positive");
  assert(broad("it('x', async () => { await expect(p).rejects.toThrow(); })"), "rejects.toThrow() positive");
  assert(!broad("it('x', () => { expect(() => f()).toThrow('boom'); })"), "toThrow(string) negative");
  assert(!broad("it('x', () => { expect(() => f()).toThrow(/boom/); })"), "toThrow(regex) negative");
  assert(!broad("it('x', () => { expect(() => f()).toThrow(TypeError); })"), "toThrow(class) negative");
  assert(!broad("it('x', () => { expect(() => f()).toThrowError('boom'); })"), "toThrowError(string) negative");
  assert(!broad("it('x', () => { expect(() => f()).not.toThrow(); })"), ".not.toThrow() asserts no throw: negative");
  assert(!broad("it('x', () => { expect(f()).toBe(1); })"), "no throw matcher negative");
});

test('duplicate title', () => {
  // 7. duplicate title: two tests in one describe with the same literal title.
  const dupLines = (src) =>
    smellsIn(parseSource(src, "snippet.test.js"), src)
      .filter(([, smell]) => smell === LOST_DUPLICATE)
      .map(([line]) => line);
  const body = (t) => `it(${t}, () => { expect(a).toBe(1); });\n`;
  assert.deepEqual(
    dupLines(`describe('g', () => {\n${body("'a'")}${body("'a'")}});`),
    [3],
    "the repeated title is reported at the later test",
  );
  assert.deepEqual(dupLines(`describe('g', () => {\n${body("'a'")}${body("'b'")}});`), [], "distinct titles");
  assert.deepEqual(
    dupLines(`describe('g', () => {\n${body("'a'")}});\ndescribe('h', () => {\n${body("'a'")}});`),
    [],
    "the same title in two describes",
  );
  assert.deepEqual(
    dupLines(`describe('g', () => {\n${body("'a'")}describe('h', () => {\n${body("'a'")}});\n});`),
    [],
    "the same title in an outer and a nested describe",
  );
  assert.deepEqual(
    dupLines(`describe('g', () => {\n${body("`a`")}${body("'a'")}});`),
    [3],
    "a template title with no substitution is a literal",
  );
  assert.deepEqual(dupLines(`describe('g', () => {\n${body("`a${n}`")}${body("`a${n}`")}});`), [], "computed title");
  assert.deepEqual(
    dupLines(`describe('g', () => {\n${body("'a'")}it.skip('a', () => { expect(a).toBe(1); });\n});`),
    [3],
    "a skipped repeat counts",
  );
  assert.deepEqual(
    dupLines(`describe('g', () => {\n${body("'a'")}${body("'a'")}${body("'a'")}});`),
    [3, 4],
    "every repeat is reported",
  );
  assert.deepEqual(
    dupLines(`describe.only('g', () => {\n${body("'a'")}${body("'a'")}});`),
    [3],
    "describe.only is a describe",
  );
  assert.deepEqual(dupLines(`${body("'a'")}${body("'a'")}`), [], "outside any describe: not this smell");
  assert.deepEqual(
    dupLines("import { describe, it } from 'vitest';\ndescribe('g', () => {\nit.todo('a');\nit.todo('a');\n});"),
    [],
    "a todo has no body to replace",
  );
  assert.deepEqual(
    dupLines(
      "import { describe, test } from 'node:test';\ndescribe('g', () => {\ntest('a', () => {});\ntest('a', () => {});\n});",
    ),
    [],
    "node:test files are out: the ticket names vitest",
  );
  assert.deepEqual(
    dupLines(`describe('g', () => {\nit.each([1, 2])('a', (n) => { expect(n).toBe(n + 0); });\nit.each([1, 2])('a', (n) => { expect(n).toBe(n + 0); });\n});`),
    [],
    "it.each is not a test call here",
  );
});

test('gate mode: fixtures exemption, exit statuses and a missing root (#685)', () => {
  // gate mode: assertion-free only (the duplicate-name case is below), and never a fixture.
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
    assert.deepEqual(gate(tmp)[1], { "assertion-free": 1 }, "gate counts what the fixtures exemption dropped");
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
    assert.deepEqual(suppressed, { "assertion-free": 1 }, "the fixtures specimen is still counted as suppressed");

    unlinkSync(join(tmp, "hollow.test.js"));
    assert.deepEqual(gate(tmp)[0], [], "gate is clean once the hollow test is gone");

    // The duplicate-name smell joins the gate, with its own fixtures exemption
    // and its own suppression count. A broad `toThrow()` stays report-only.
    const dup =
      "describe('g', () => {\nit('a', () => { expect(a).toBe(1); });\nit('a', () => { expect(a).toBe(2); });\n});\n";
    writeFileSync(join(tmp, "fixtures", "dup-specimen.test.js"), dup);
    writeFileSync(join(tmp, "broad.test.js"), "it('x', () => { expect(() => f()).toThrow(); });\n");
    assert.deepEqual(gate(tmp)[0], [], "a broad toThrow and a fixtures duplicate do not fail the gate");
    assert.deepEqual(gate(tmp)[1], { "assertion-free": 1, "duplicate-name": 1 }, "both exemptions are counted");
    {
      const [code, err] = mainStderr(["node", "audit.mjs", "--gate", tmp]);
      assert.equal(code, 0, "fixtures-only duplicates still pass the gate");
      assert(err.includes("1 duplicate-name finding(s) suppressed under fixtures/"), `gate reports it: ${err}`);
    }
    writeFileSync(join(tmp, "dup.test.js"), dup);
    {
      const [gatedDup] = gate(tmp);
      assert.deepEqual(
        gatedDup.map(([path, line, smell]) => [basename(path), line, smell]),
        [["dup.test.js", 3, LOST_DUPLICATE]],
        "a duplicate title outside fixtures fails the gate",
      );
    }
    assert.equal(quietMain(["node", "audit.mjs", "--gate", tmp]), 1, "and the exit status says so");
    unlinkSync(join(tmp, "dup.test.js"));
    unlinkSync(join(tmp, "broad.test.js"));
    unlinkSync(join(tmp, "fixtures", "dup-specimen.test.js"));

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
});

test('a root that cannot be read is refused, not reported clean (#685)', () => {
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
});

test('candidate smells: stub asserted called, vacuous loop, private-API access', () => {
  // 8. candidate smells: stub asserted called, vacuous loop, private-API access
  const has = (src, smell) => smellsOf(src).includes(smell);
  assert(
    has("it('t', () => { const g = vi.fn().mockReturnValue(1); expect(f(g)).toBe(1); expect(g).toHaveBeenCalled(); });", STUB_SMELL),
    "a named vi.fn() stub that is asserted called",
  );
  assert(
    !has("it('t', () => { const g = vi.fn().mockReturnValue(1); const h = vi.fn(); expect(f(g, h)).toBe(1); expect(h).toHaveBeenCalled(); });", STUB_SMELL),
    "the asserted mock is not the stub",
  );
  assert(
    has("it('t', () => { const r = f(); r.forEach((i) => { expect(i).toBe(1); }); });", VACUOUS_SMELL),
    "forEach over the output holds every assertion",
  );
  assert(
    !has("it('t', () => { const r = f(); expect(r.length).toBe(2); r.forEach((i) => { expect(i).toBe(1); }); });", VACUOUS_SMELL),
    "a length check outside the loop clears it",
  );
  assert(
    !has("it('t', () => { for (const k of Object.keys(CASES)) { expect(f(k)).toBe(1); } });", VACUOUS_SMELL),
    "a loop over a module constant is a fixed input",
  );
  assert(has("it('t', () => { expect(c['_store']).toBe(1); });", PRIVATE_SMELL), "a bracketed private name");
  assert(!has("it('t', () => { expect(c['__proto__']).toBe(1); });", PRIVATE_SMELL), "a dunder name is not private");
  assert(
    has("it('t', () => {\n  // @ts-expect-error private\n  expect(c.store).toBe(1);\n});", PRIVATE_SMELL),
    "a member access under @ts-expect-error",
  );
  assert(
    !has("it('t', () => {\n  // @ts-expect-error wrong type\n  expect(() => f(1)).toThrow('x');\n});", PRIVATE_SMELL),
    "an expect matcher chain under @ts-expect-error is no member access",
  );

  assert(
    has("it('t', () => { const g = vi.fn(() => 1); expect(f(g)).toBe(1); expect(g).toHaveBeenCalled(); });", STUB_SMELL),
    "vi.fn(impl) supplies input",
  );
  assert(
    has("it('t', () => { vi.mocked(get).mockResolvedValue(1); expect(f()).toBe(1); expect(get).toHaveBeenCalled(); });", STUB_SMELL),
    "vi.mocked(get) names the stub",
  );
  assert(
    has("it('t', () => { let g; g = vi.fn().mockReturnValue(1); expect(f(g)).toBe(1); expect(g).toHaveBeenCalled(); });", STUB_SMELL),
    "a stub bound by assignment",
  );
  assert(
    !has("it('t', () => { const r = f(); expect.hasAssertions(); r.forEach((i) => { expect(i).toBe(1); }); });", VACUOUS_SMELL),
    "expect.hasAssertions fails an empty loop",
  );
  assert(
    !has("it('t', () => { [1, 2].map(double).forEach((i) => { expect(i).toBe(1); }); });", VACUOUS_SMELL),
    "a method on a literal is a fixed input",
  );
  assert(!has("it('t', () => { expect(this['_x']).toBe(1); });", PRIVATE_SMELL), "this[...] is the test's own state");
  assert(
    !has("it('t', () => {\n  // @ts-expect-error wrong type\n  expect(() => client.send(42)).toThrow('x');\n});", PRIVATE_SMELL),
    "a call under test inside expect(() => ...) is no member read",
  );
});

