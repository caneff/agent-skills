import { test, expect, describe } from "vitest";
import { emitMarker, isSetupNoise, MARK_PREFIX } from "../markers.mts";

// The sandcastle-watch skill reads a run's progress off machine-readable
// sentinel lines the orchestrator prints beside its human output — the same
// host-coupled contract idea as SANDCASTLE_SPEC (CODING_STANDARDS #3). emitMarker
// owns the one wire format both the emitter and the skill's `digest` parser
// agree on. These assert the exact strings, since a reworded prefix silently
// blinds the status bar.
describe("emitMarker", () => {
  test("the build-set count marker carries the plan size", () => {
    expect(emitMarker("plan", 3)).toBe(`${MARK_PREFIX} plan 3`);
  });

  test("the in-flight marker lists every id on one line", () => {
    expect(emitMarker("flight", "101", "102", "104")).toBe(
      `${MARK_PREFIX} flight 101 102 104`
    );
  });

  test("a PR marker pairs the issue id with its PR number", () => {
    expect(emitMarker("pr", "325", 42)).toBe(`${MARK_PREFIX} pr 325 42`);
  });

  test("a real-failure marker names the failing id", () => {
    expect(emitMarker("fail", "103")).toBe(`${MARK_PREFIX} fail 103`);
  });

  test("a setup-noise marker names the transient id", () => {
    expect(emitMarker("setup", "107")).toBe(`${MARK_PREFIX} setup 107`);
  });

  test("a review-warn marker names the id needing a human", () => {
    expect(emitMarker("warn", "104")).toBe(`${MARK_PREFIX} warn 104`);
  });

  test("the done marker takes no args and leaves no trailing space", () => {
    expect(emitMarker("done")).toBe(`${MARK_PREFIX} done`);
  });
});

// isSetupNoise splits a transient sandbox-setup hiccup from a real failure so
// the emitter tags `setup <id>` vs `fail <id>`. See markers.mts for the full
// rationale; the cases below pin the signature: a silent nonzero git ExecError
// is noise, everything else is a real failure.
describe("isSetupNoise", () => {
  // The live evidence from issue #268: exit 128 on git config safe.directory,
  // empty stderr (the line ends at the command).
  const gitSetupHiccup =
    '(FiberFailure) ExecError: Command failed (exit 128): git config --global --add safe.directory "/home/agent/workspace"\n';

  test("a silent git setup ExecError is setup noise", () => {
    expect(isSetupNoise(gitSetupHiccup)).toBe(true);
  });

  test("a git ExecError that wrote a fatal: to stderr is a real failure", () => {
    const realGitFailure =
      "(FiberFailure) ExecError: Command failed (exit 1): git push origin HEAD\nfatal: the remote end hung up unexpectedly";
    expect(isSetupNoise(realGitFailure)).toBe(false);
  });

  test("a non-git silent ExecError is not claimed as setup noise", () => {
    const otherExec =
      "(FiberFailure) ExecError: Command failed (exit 2): pytest -q\n";
    expect(isSetupNoise(otherExec)).toBe(false);
  });

  test("a harness fault (PromptError) is not setup noise", () => {
    expect(
      isSetupNoise("(FiberFailure) PromptError: preprocessor `!gh` exited 1")
    ).toBe(false);
  });

  test("a per-issue crash with no exec signature is a real failure", () => {
    expect(
      isSetupNoise("(FiberFailure) Error: sandbox connection reset")
    ).toBe(false);
  });

  test("a review-fail reason is a real failure, not setup noise", () => {
    // A review-fail never actually reaches the classifier (it emits `warn` on a
    // fulfilled path), but the acceptance criterion names it: it must not be
    // swallowed as setup noise if it ever did.
    expect(isSetupNoise("review-fail (spec, standards)")).toBe(false);
  });

  test("an Error object is read through its string form, not just raw strings", () => {
    const err = new Error(
      'ExecError: Command failed (exit 128): git config --global --add safe.directory "/w"\n'
    );
    expect(isSetupNoise(err)).toBe(true);
  });
});
