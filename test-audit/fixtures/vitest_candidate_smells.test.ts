// Fixture: four more smells, for audit.mjs's pass one and the judgment pass.
// Each smell has a positive and the nearest negative that must stay quiet. The
// judgment-pass rows are in `answer-key.md`; `candidate-smells-fixtures.test.sh`
// pins the scanner's output on this file line by line, so edit the three
// together.
import { describe, it, expect, vi } from "vitest";
import { Cache, loadUser, listItems, total, double, nextId, client } from "../src/app";

describe("leaking domain knowledge (judgment pass only)", () => {
  it("recomputes the formula", () => {
    expect(total(100, 0.2)).toBe(100 + 100 * 0.2);
  });

  it("matches a worked example", () => {
    expect(total(100, 0.2)).toBe(120);
  });
});

describe("private-API access", () => {
  it("casts to any", () => {
    const cache = new Cache();
    expect((cache as any).store).toEqual({});
  });

  it("silences the type error", () => {
    const cache = new Cache();
    // @ts-expect-error store is private
    expect(cache.store).toEqual({});
  });

  it("indexes a private name", () => {
    const cache = new Cache();
    expect(cache["_store"]).toEqual({});
  });

  it("reads the public interface", () => {
    const cache = new Cache();
    expect(cache.size).toBe(0);
    expect(cache["size"]).toBe(0);
  });

  it("silences a type error that is no member access", () => {
    // @ts-expect-error the argument is the wrong type
    expect(() => client.send(1)).toThrow("not a string");
  });
});

describe("a stub that supplies input is also asserted called", () => {
  it("asserts the stub called", () => {
    const get = vi.fn().mockReturnValue({ id: 1 });
    expect(loadUser(get, 1).id).toBe(1);
    expect(get).toHaveBeenCalledWith(1);
  });

  it("asserts a spied method called", () => {
    const repo = { get: (id: number) => id };
    vi.spyOn(repo, "get").mockReturnValueOnce(1);
    expect(loadUser(repo.get, 1)).toBe(1);
    expect(repo.get).toHaveBeenCalled();
  });

  it("never asserts the stub called", () => {
    const get = vi.fn().mockReturnValue({ id: 1 });
    expect(loadUser(get, 1).id).toBe(1);
  });

  it("asserts a different mock called", () => {
    const get = vi.fn().mockReturnValue({ id: 1 });
    const send = vi.fn();
    const user = loadUser(get, nextId(), send);
    expect(Number(user.id)).toBe(1);
    expect(send).toHaveBeenCalledTimes(1);
  });
});

describe("vacuous loop assertion", () => {
  it("asserts only inside forEach over the output", () => {
    const items = listItems();
    items.forEach((item) => {
      expect(item.price).toBeGreaterThan(0);
    });
  });

  it("asserts only inside for-of over the output", () => {
    const items = listItems();
    for (const item of items) {
      expect(item.price).toBeGreaterThan(0);
    }
  });

  it("checks the length before the loop", () => {
    const items = listItems();
    expect(items).toHaveLength(2);
    for (const item of items) {
      expect(item.price).toBeGreaterThan(0);
    }
  });

  it("loops over literal cases", () => {
    for (const n of [1, 2, 3]) {
      expect(double(n)).toBeGreaterThan(n);
    }
  });
});
