import { test, expect } from "vitest";
import { planRetention } from "../log-retention.mts";

// A fixed cutoff so the fixtures read as plain before/after-the-line data.
const CUTOFF = Date.parse("2026-01-15T00:00:00Z");
const hdr = (ts) => `--- Run started: ${ts} ---`;

test("all runs recent → keep-all (leave the file untouched)", () => {
  const lines = [
    hdr("2026-01-20T10:00:00Z"),
    "some log output",
    hdr("2026-01-21T10:00:00Z"),
    "more output",
  ];
  expect(planRetention(lines, CUTOFF)).toEqual({ action: "keep-all" });
});

test("all runs stale → empty (the file gets deleted)", () => {
  const lines = [
    hdr("2026-01-01T10:00:00Z"),
    "old output",
    hdr("2026-01-10T10:00:00Z"),
    "older output",
  ];
  expect(planRetention(lines, CUTOFF)).toEqual({ action: "empty" });
});

test("one recent run after stale ones → keep from its header index", () => {
  const lines = [
    hdr("2026-01-02T10:00:00Z"), // 0 — stale
    "old output", //                1
    hdr("2026-01-20T10:00:00Z"), // 2 — first recent header
    "recent output", //             3
  ];
  expect(planRetention(lines, CUTOFF)).toEqual({
    action: "keep-from",
    index: 2,
  });
});

test("a file with no run header at all → empty", () => {
  const lines = ["just some text", "no headers here", ""];
  expect(planRetention(lines, CUTOFF)).toEqual({ action: "empty" });
});

test("boundary: a header exactly at the cutoff counts as recent (>=)", () => {
  const lines = [
    hdr("2026-01-10T00:00:00Z"), // 0 — before cutoff, stale
    "old output", //                1
    hdr("2026-01-15T00:00:00Z"), // 2 — exactly at cutoff → kept
    "boundary output", //           3
  ];
  expect(planRetention(lines, CUTOFF)).toEqual({
    action: "keep-from",
    index: 2,
  });
});
