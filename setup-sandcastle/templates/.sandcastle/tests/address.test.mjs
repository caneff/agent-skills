import { test, expect, beforeAll, afterAll } from "vitest";
import { rmSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { hasCopier, renderPythonArm } from "./render-fixture.mjs";

// address.mts branches on LANGUAGE, so there is no plain `.mts` to import —
// render the Python arm and import that, as the other suites do.
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..", "..");
const withRender = test.skipIf(!hasCopier());

let rendered;
let selectPrsWithComments;
let addressOpenPRs;
beforeAll(async () => {
  if (!hasCopier()) return;
  rendered = renderPythonArm(repoRoot, { linkModules: true });
  ({ selectPrsWithComments, addressOpenPRs } = await import(
    pathToFileURL(join(rendered, ".sandcastle", "address.mts")).href
  ));
}, 60_000);
afterAll(() => rendered && rmSync(rendered, { recursive: true, force: true }));

function fakeGh(commentCounts) {
  return (cmd) => {
    if (cmd.includes("repo view")) return "acme/widgets";
    if (cmd.includes("pr list")) return "11\n12";
    const m = cmd.match(/\/(?:pulls|issues)\/(\d+)\/(?:comments|reviews)/);
    if (m) return String(commentCounts[m[1]] ?? 0);
    const v = cmd.match(/pr view (\d+)/);
    if (v) return `sandcastle/issue-${v[1]}`;
    return "";
  };
}

withRender("addressOpenPRs (no-arg sweep): runs a sandbox only for PRs with comments, reply-only via the prompt", async () => {
  const runs = [];
  await addressOpenPRs(undefined, {
    sh: fakeGh({ 11: 2, 12: 0 }),
    run: async (opts) => {
      runs.push(opts);
      return {};
    },
  });
  expect(runs).toHaveLength(1);
  expect(runs[0].name).toBe("address-pr-11");
  expect(runs[0].branchStrategy).toEqual({
    type: "branch",
    branch: "sandcastle/issue-11",
  });
  expect(runs[0].promptArgs).toEqual({ PR_NUMBER: "11" });
  // The reply-only / no-resolve / no-merge contract lives in this prompt file.
  expect(runs[0].promptFile).toBe("./.sandcastle/address-comments-prompt.md");
});

withRender("addressOpenPRs: explicit PR numbers bypass the sweep and run in order", async () => {
  const runs = [];
  await addressOpenPRs(["7"], {
    sh: fakeGh({}),
    run: async (opts) => {
      runs.push(opts.name);
      return {};
    },
  });
  expect(runs).toEqual(["address-pr-7"]);
});

withRender("selectPrsWithComments: keeps only candidates whose comment count is > 0", () => {
  const counts = { 11: 0, 12: 3, 13: 0, 14: 1 };
  const kept = selectPrsWithComments(["11", "12", "13", "14"], (pr) => counts[pr]);
  expect(kept).toEqual(["12", "14"]);
});

withRender("selectPrsWithComments: empty when no candidate has comments", () => {
  expect(selectPrsWithComments(["11", "12"], () => 0)).toEqual([]);
});
