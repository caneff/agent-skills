import { describe, expect, it } from "vitest";
import { arrowFn, branchlessFn, outer } from "./sample";

describe("sample", () => {
  it("covers outer/inner on the y>0, y<=10 branch only", () => {
    expect(outer(5)).toBe(6);
  });

  it("covers both arrow branches", () => {
    expect(arrowFn(5)).toBe(10);
    expect(arrowFn(-1)).toBe(0);
  });

  it("covers the branchless function", () => {
    expect(branchlessFn(1)).toBe(2);
  });
});
