import { test, expect, describe } from "vitest";
import {
  parseBlockedByRows,
  parseIssueEdges,
  parseIssueList,
  parseOpenIssues,
  parseParentEdges,
  parsePrsClosingIssues,
} from "../github-parse.mts";

describe("parseIssueEdges", () => {
  test("returns every issue's number, state and parent", () => {
    const raw = JSON.stringify([
      { number: 90, state: "OPEN", parent: null },
      { number: 91, state: "CLOSED", parent: 90 },
    ]);
    expect(parseIssueEdges(raw)).toEqual([
      { number: 90, state: "OPEN", parent: null },
      { number: 91, state: "CLOSED", parent: 90 },
    ]);
  });

  test("unusable output → null, which callers must not read as 'no issues'", () => {
    // `issueIsClosed` fails OPEN on null and would call every parent dead on
    // an empty array, so the two answers cannot be collapsed.
    expect(parseIssueEdges(null)).toBeNull();
    expect(parseIssueEdges("not json")).toBeNull();
    expect(
      parseIssueEdges(JSON.stringify([{ number: 90, state: "DRAFT", parent: null }]))
    ).toBeNull();
    expect(parseIssueEdges("[]")).toEqual([]);
  });
});

describe("parseParentEdges", () => {
  test("maps child id to parent id as strings, dropping parentless issues", () => {
    const raw = JSON.stringify([
      { number: 91, parent: 90 },
      { number: 92, parent: null },
    ]);
    const map = parseParentEdges(raw);
    expect(map.get("91")).toBe("90");
    expect(map.has("92")).toBe(false);
  });

  test("null / invalid JSON / missing parent key → empty Map", () => {
    expect(parseParentEdges(null).size).toBe(0);
    expect(parseParentEdges("not json").size).toBe(0);
    expect(parseParentEdges(JSON.stringify([{ number: 91 }])).size).toBe(0);
  });
});

describe("parseBlockedByRows", () => {
  test("keys each issue's blockedBy edges by issue number", () => {
    const raw = JSON.stringify([
      { number: 50, blockedBy: [40, 41] },
      { number: 51, blockedBy: [] },
    ]);
    const map = parseBlockedByRows(raw);
    expect(map.get(50)).toEqual([40, 41]);
    expect(map.get(51)).toEqual([]);
  });

  test("null / invalid JSON / wrong shape → empty Map", () => {
    expect(parseBlockedByRows(null).size).toBe(0);
    expect(parseBlockedByRows("not json").size).toBe(0);
    // Used to throw mid-run and take the whole sweep down with it.
    expect(
      parseBlockedByRows(JSON.stringify([{ number: 50, blockedBy: null }])).size
    ).toBe(0);
  });
});

describe("parseIssueList", () => {
  test("null / blank / invalid JSON → []", () => {
    expect(parseIssueList(null)).toEqual([]);
    expect(parseIssueList("")).toEqual([]);
    expect(parseIssueList("not json")).toEqual([]);
  });

  test("returns the number/title rows the work list runs on", () => {
    const raw = JSON.stringify([
      { number: 7, title: "Add dark mode" },
      { number: 8, title: "Fix the footer" },
    ]);
    expect(parseIssueList(raw)).toEqual([
      { number: 7, title: "Add dark mode" },
      { number: 8, title: "Fix the footer" },
    ]);
  });

  test("a row of the wrong shape degrades to [] rather than reaching the planner", () => {
    // Well-formed JSON, wrong contents — what an API change looks like.
    expect(parseIssueList(JSON.stringify([{ number: "7" }]))).toEqual([]);
    expect(parseIssueList(JSON.stringify({ number: 7 }))).toEqual([]);
  });
});

describe("parseOpenIssues", () => {
  test("null / blank / invalid JSON → []", () => {
    expect(parseOpenIssues(null)).toEqual([]);
    expect(parseOpenIssues("")).toEqual([]);
    expect(parseOpenIssues("not json")).toEqual([]);
    expect(parseOpenIssues('{"not":"an array"}')).toEqual([]);
  });

  test("flattens label objects to names", () => {
    const raw = JSON.stringify([
      {
        number: 7,
        title: "Add dark mode",
        labels: [{ name: "ready-for-agent" }, { name: "ui" }],
      },
    ]);
    expect(parseOpenIssues(raw)).toEqual([
      { number: 7, title: "Add dark mode", labels: ["ready-for-agent", "ui"] },
    ]);
  });

  test("tolerates an issue with no labels array", () => {
    const raw = JSON.stringify([{ number: 9, title: "Untriaged" }]);
    expect(parseOpenIssues(raw)).toEqual([
      { number: 9, title: "Untriaged", labels: [] },
    ]);
  });
});

describe("parsePrsClosingIssues", () => {
  test("null / invalid JSON / missing nodes → empty Map", () => {
    expect(parsePrsClosingIssues(null).size).toBe(0);
    expect(parsePrsClosingIssues("not json").size).toBe(0);
    expect(parsePrsClosingIssues("{}").size).toBe(0);
    expect(
      parsePrsClosingIssues(JSON.stringify({ data: { repository: {} } })).size
    ).toBe(0);
  });

  test("maps each closed issue to the PRs that close it, preserving state", () => {
    const raw = JSON.stringify({
      data: {
        repository: {
          pullRequests: {
            nodes: [
              {
                number: 100,
                state: "OPEN",
                closingIssuesReferences: {
                  nodes: [{ number: 7 }, { number: 8 }],
                },
              },
              {
                number: 101,
                state: "MERGED",
                closingIssuesReferences: { nodes: [{ number: 7 }] },
              },
              {
                number: 102,
                state: "CLOSED",
                closingIssuesReferences: { nodes: [] },
              },
            ],
          },
        },
      },
    });
    const map = parsePrsClosingIssues(raw);
    expect(map.get(7)).toEqual([
      { number: 100, state: "OPEN" },
      { number: 101, state: "MERGED" },
    ]);
    expect(map.get(8)).toEqual([{ number: 100, state: "OPEN" }]);
    expect(map.has(102)).toBe(false); // a PR closing nothing adds no entry
  });

  test("an unknown PR state degrades to an empty Map rather than a bogus PrState", () => {
    // `state` feeds PrState, which reconcile branches on. A value outside the
    // union used to be cast straight through.
    const raw = JSON.stringify({
      data: {
        repository: {
          pullRequests: {
            nodes: [
              {
                number: 100,
                state: "DRAFT",
                closingIssuesReferences: { nodes: [{ number: 7 }] },
              },
            ],
          },
        },
      },
    });
    expect(parsePrsClosingIssues(raw).size).toBe(0);
  });

  test("a PR with no closingIssuesReferences field is skipped", () => {
    const raw = JSON.stringify({
      data: {
        repository: {
          pullRequests: { nodes: [{ number: 200, state: "OPEN" }] },
        },
      },
    });
    expect(parsePrsClosingIssues(raw).size).toBe(0);
  });
});
