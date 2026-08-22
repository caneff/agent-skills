import { test, expect, describe } from "vitest";
import { prGroups, chooseTip } from "../pr-groups.mts";

// The built issues a run produced, in build order. `parent` is the native
// GitHub sub-issue parent — the spec — or null for a standalone ticket.
const issue = (id, parent = null) => ({
  id,
  branch: `sandcastle/issue-${id}`,
  parent,
});

describe("prGroups", () => {
  test("issue mode: every built issue is its own PR group, in build order", () => {
    const built = [issue(41), issue(42), issue(43)];
    expect(prGroups(built, "issue")).toEqual([
      { key: 41, members: [issue(41)] },
      { key: 42, members: [issue(42)] },
      { key: 43, members: [issue(43)] },
    ]);
  });

  test("issue mode ignores the parent edge entirely — siblings still split", () => {
    const built = [issue(41, 100), issue(42, 100)];
    expect(prGroups(built, "issue").map((g) => g.key)).toEqual([41, 42]);
  });

  test("spec mode: siblings under one parent collapse into one group", () => {
    const built = [issue(41, 100), issue(42, 100)];
    expect(prGroups(built, "spec")).toEqual([
      { key: 100, members: [issue(41, 100), issue(42, 100)] },
    ]);
  });

  test("spec mode: an orphan (no parent) is its own group, keyed by its id", () => {
    const built = [issue(41, 100), issue(50)];
    expect(prGroups(built, "spec")).toEqual([
      { key: 100, members: [issue(41, 100)] },
      { key: 50, members: [issue(50)] },
    ]);
  });

  test("spec mode: members keep build order; groups keep first-seen order", () => {
    // 41 and 43 share parent 100; 42 is an orphan seen between them.
    const built = [issue(41, 100), issue(42), issue(43, 100)];
    expect(prGroups(built, "spec")).toEqual([
      { key: 100, members: [issue(41, 100), issue(43, 100)] },
      { key: 42, members: [issue(42)] },
    ]);
  });

  test("empty input yields no groups in either mode", () => {
    expect(prGroups([], "issue")).toEqual([]);
    expect(prGroups([], "spec")).toEqual([]);
  });
});

describe("chooseTip", () => {
  const m = (id) => ({ id, branch: `sandcastle/issue-${id}` });

  // isAncestor built from an explicit "x is an ancestor of y" edge list, so the
  // test states ancestry directly instead of recomputing it the way chooseTip
  // does.
  const ancestryFrom = (pairs) => (a, b) =>
    pairs.some(([x, y]) => x === a && y === b);

  test("a lone member is its own tip; ancestry is never consulted", () => {
    let called = false;
    const tip = chooseTip([m(41)], () => {
      called = true;
      return false;
    });
    expect(tip).toEqual(m(41));
    expect(called).toBe(false);
  });

  test("a linear stack a<-b<-c has the last branch as its tip", () => {
    // c contains b contains a: every earlier branch is an ancestor of c.
    const isAncestor = ancestryFrom([
      ["sandcastle/issue-41", "sandcastle/issue-42"],
      ["sandcastle/issue-41", "sandcastle/issue-43"],
      ["sandcastle/issue-42", "sandcastle/issue-43"],
    ]);
    expect(chooseTip([m(41), m(42), m(43)], isAncestor)).toEqual(m(43));
  });

  test("branch order does not matter — the tip is found however members are listed", () => {
    const isAncestor = ancestryFrom([
      ["sandcastle/issue-41", "sandcastle/issue-42"],
      ["sandcastle/issue-41", "sandcastle/issue-43"],
      ["sandcastle/issue-42", "sandcastle/issue-43"],
    ]);
    expect(chooseTip([m(43), m(41), m(42)], isAncestor)).toEqual(m(43));
  });

  test("independent branches (no stack) have no tip", () => {
    // Two siblings cut from main, neither an ancestor of the other.
    expect(chooseTip([m(41), m(42)], () => false)).toBeNull();
  });

  test("a diamond with no single containing branch has no tip", () => {
    // b and c both descend from a, but neither contains the other.
    const isAncestor = ancestryFrom([
      ["sandcastle/issue-41", "sandcastle/issue-42"],
      ["sandcastle/issue-41", "sandcastle/issue-43"],
    ]);
    expect(chooseTip([m(41), m(42), m(43)], isAncestor)).toBeNull();
  });
});
