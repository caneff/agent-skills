import { test, expect, describe } from "vitest";
import { logFilePath } from "../log-path.mts";

// logFilePath reproduces sandcastle's default per-run log filename so existing
// `tail -f` paths keep working: <sanitized-branch>-<slugged-name>.log under the
// logs dir. It is the pure half of main.mts's logging() — an external filename
// contract with no test until now.
describe("logFilePath", () => {
  test("a plain branch and name join under the logs dir", () => {
    expect(logFilePath("planner", "main")).toBe(
      ".sandcastle/logs/main-planner.log"
    );
  });

  test("a slashed branch sanitizes its path separators to dashes", () => {
    expect(logFilePath("implementer", "sandcastle/issue-112")).toBe(
      ".sandcastle/logs/sandcastle-issue-112-implementer.log"
    );
  });

  test("an upper-cased name with spaces slugs to lowercase dashes", () => {
    expect(logFilePath("PR Author", "main")).toBe(
      ".sandcastle/logs/main-pr-author.log"
    );
  });

  test("other filename-hostile branch characters become dashes", () => {
    expect(logFilePath("x", 'a:b*c?d"e<f>g|h')).toBe(
      ".sandcastle/logs/a-b-c-d-e-f-g-h-x.log"
    );
  });

  test("the logs dir is overridable", () => {
    expect(logFilePath("planner", "main", "/tmp/logs")).toBe(
      "/tmp/logs/main-planner.log"
    );
  });
});
