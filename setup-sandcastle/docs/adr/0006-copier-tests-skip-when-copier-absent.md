# The copier round-trip tests skip when copier is absent, and that skip stays

## Status

accepted

## Context

Six test blocks — five in `copier-template.test.mjs` (render at the git root,
the two delimiter-safety blocks, the node adopter, the `copier update`
round-trip) and one full-install block in `install.test.mjs` — are gated on
`describe.skipIf(!hasCopier())`. `hasCopier()` (in `render-fixture.mjs`) shells
`copier --version` and reports whether the tool is on `PATH`. On a machine
without copier, all six vanish and the suite reports green having exercised none
of the install/update round-trip — the very thing a fresh environment is most
likely to get wrong (issue #112).

The friction is real: a silent skip reads the same as a pass. The question is
whether a missing prereq should instead fail the suite loudly.

Two facts shape the answer. First, copier is a **documented install-time
prerequisite**, not a test-only dependency: `render-fixture.mjs` names it as
`uv tool install copier`, and a contributor who lacks it has an unfinished
environment, not a broken build. Second, **this repo has no CI** — no
`.github/workflows/`, nothing that reads `process.env.CI`. The suite runs only
on developer machines, and the template these tests cover ships to adopters
through `copier`, never through this repo's own pipeline. So "fail loudly, but
only in CI" has nothing to hook onto; the choice is fail everywhere or skip
everywhere.

## Decision

Keep the skip. A missing copier does not fail the suite.

## Considered options

- **Fail loudly everywhere.** Rejected. With no CI, the only machine a hard
  failure reaches is a half-set-up contributor's — and it punishes them for
  lacking a documented prereq rather than for any defect in the code. It buys no
  protection for the one path that matters, the template shipped to adopters,
  because that path never runs through here.
- **Fail loudly in CI only.** Not available. There is no CI and no `CI`
  environment signal to gate on. Revisit this ADR if CI is ever added: a CI
  runner is the right place for a missing prereq to be a hard failure, since a
  provisioned runner without copier is a genuine misconfiguration, not a
  contributor mid-setup.

## Consequences

- On a machine without copier the round-trip coverage is absent and the run is
  green — a known blind spot, accepted because copier is a developer prereq and
  the suite is developer-only. The `hasCopier()` guard is the honest name for
  "this block needs the prereq"; it is not a bug to be papered over.
- If CI is ever introduced for this repo, this decision should be reopened: gate
  the skip on the absence of a `CI` signal so a CI runner missing copier fails
  loudly while a local run still skips. Recorded here so the future change is a
  deliberate reversal, not a rediscovery of the same friction.
- No test or fixture changes: the guards already carry the intended behavior.
  This ADR records *why* they stay, matching the test-quality reasoning of
  ADR-0005 (guard for real bug-yield, not for drift-detection theatre).
