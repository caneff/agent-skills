import { test, expect, describe } from "vitest";
import {
  parseBlockedByRows,
  parseIssueEdges,
  parseOpenIssues,
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
    // The spent-parent check must tell "the fetch failed" (null) from "a repo
    // with no issues" ([]) — collapsing the two would flag phantom parents, so
    // the parser keeps them distinct.
    expect(parseIssueEdges(null)).toBeNull();
    expect(parseIssueEdges("not json")).toBeNull();
    expect(
      parseIssueEdges(JSON.stringify([{ number: 90, state: "DRAFT", parent: null }]))
    ).toBeNull();
    expect(parseIssueEdges("[]")).toEqual([]);
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
