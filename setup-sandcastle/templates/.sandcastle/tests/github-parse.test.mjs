import { test, expect, describe } from "vitest";
import { parseOpenIssues, parsePrsClosingIssues } from "../github-parse.mts";

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
