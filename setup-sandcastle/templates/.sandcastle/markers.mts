// The status-bar marker contract, split out of main.mts so the wire format has
// one home and can be tested without running a sandbox. Sibling to log-path.mts.
//
// sandcastle-watch reads a run's progress off machine-readable sentinel lines
// the orchestrator prints beside its human output — never off the human wording,
// which drifts per template version and silently blinds the bar (that drift was
// the bug this contract fixes). This is the same host-coupled sentinel idea as
// SANDCASTLE_SPEC (CODING_STANDARDS #3): the skill greps the prefix verbatim, so
// don't reword MARK_PREFIX or the kind tokens without changing the parser too.
export const MARK_PREFIX = "SANDCASTLE_MARK";

// The closed set of marker kinds. A typo'd kind silently blinds the bar — the
// exact failure this contract exists to prevent — so the union lets tsc catch it
// at the emit site instead of at runtime.
export type MarkerKind =
  | "plan"
  | "flight"
  | "pr"
  | "fail"
  | "setup"
  | "warn"
  | "done";

// One sentinel line: the prefix, the kind, then its args, space-joined. The
// skill's `digest` splits on whitespace — $2 is the kind, the rest the args
// (`plan 3`, `flight 101 102 104`, `pr 325 42`, `fail 103`, `done`).
export function emitMarker(
  kind: MarkerKind,
  ...args: (string | number)[]
): string {
  return [MARK_PREFIX, kind, ...args].join(" ");
}

// Split a transient sandbox-setup hiccup from a real failure, so the emitter can
// tag `setup <id>` vs `fail <id>` at the point the rejection reason is known —
// the skill then reads the verdict instead of guessing from stdout shape.
//
// The signature is the ExecError message the exec transport builds:
// `Command failed (exit N): <command>\n<stderr>`. A transient hiccup is a git
// setup command that exited nonzero with an EMPTY stderr — git never fails
// silently (every real fatal: writes to stderr first), so a silent nonzero git
// exec means the transport dropped the command, not that the command ran and
// failed. The next run retries the issue and normally gets clean through.
//
// The reason arrives Effect-wrapped (`(FiberFailure) ExecError: …`), so we read
// its string form, like isHarnessError in review-verdict.mts. Scoped to git on
// purpose: the "fails silently" reasoning is git's, and the only evidenced
// hiccup is `git config --global --add safe.directory` (exit 128, which the
// framework's own transient-retry set {126,137} does not cover). Anything we
// cannot positively match to this signature stays a real failure — a wrongly
// surfaced failure is safer than a hidden one.
// ponytail: git-only; widen to other setup commands only when one is evidenced.
export function isSetupNoise(reason: unknown): boolean {
  const m = String(reason).match(
    /Command failed \(exit [1-9][0-9]*\): ([^\n]*)\n?([\s\S]*)$/
  );
  if (!m) return false;
  const [, command, stderr] = m;
  if (!/\bgit\b/.test(command)) return false;
  return stderr.trim() === "";
}
