// Pass-one fixture: the exact-match smells for audit.mjs. Each smell has a
// positive and the nearest negative that must stay quiet. Not in the
// judgment-pass answer key. `exact-match-fixtures.test.sh` pins the scanner's
// output on this file line by line, so edit the two together.
import { describe, it, expect } from "vitest";
import { parse } from "../src/parse.js";

describe("duplicate title", () => {
  it("parses one", () => {
    expect(parse("1")).toBe(1);
  });

  it("parses one", () => {
    expect(parse("2")).toBe(2);
  });
});

describe("distinct titles", () => {
  it("parses one", () => {
    expect(parse("1")).toBe(1);
  });

  it("parses two", () => {
    expect(parse("2")).toBe(2);
  });
});

describe("broad exception expectation", () => {
  it("passes on any error", () => {
    expect(() => parse("")).toThrow();
  });

  it("names the error it expects", () => {
    expect(() => parse("")).toThrow("empty");
  });

  it("asserts nothing is thrown", () => {
    expect(() => parse("1")).not.toThrow();
  });
});
