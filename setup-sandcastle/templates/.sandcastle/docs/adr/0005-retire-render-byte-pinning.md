# Retire full-render byte-pinning; guard renders with set-nets, typecheck, and a contract-string allowlist

`copier-template.test.mjs` used to pin every rendered file byte-for-byte to a
pre-arc baseline commit (`PRE_ARC`), forcing each intended template edit to be
re-declared as a from→to string pair in a ~700-line `ARC_REWRITTEN_PROSE`
object. A two-pass test-quality audit found this mechanism was a change-detector,
not a bug-catcher: each declared pair was a retyped copy of the diff already
under PR review, its real bug-yield was near zero, and it taxed every template
edit with a mirrored test edit (and set traps — a declaration lost to a duplicate
object key sat green and inert). We removed the byte-identity comparison and its
declaration scaffolding, and now guard the render three cheaper ways instead: the
**set-equality nets** (rendered-file set, answers set, withdrawn/added lists) that
have caught real install breakage from renames and withdrawals; the
**rendered-typecheck** test that runs `tsc` on the live render; and a small
**contract-string allowlist** pinning only the host-coupled strings a grep or
adopter genuinely depends on — chiefly the `SANDCASTLE_CHECK:` sentinel.

## Considered options

- **Keep the byte-pin.** Rejected: total drift-detection, but the drift it caught
  was already surfaced by the PR diff and CI, at a standing tax on every edit.
- **Byte-pin only the behavior-bearing files.** Rejected as unnecessary: every
  such helper (`reconcile`, `retry-policy`, `base-resolution`, `github-parse`,
  `review-verdict`, `sandbox-identity`, `log-retention`) already has its own unit
  suite. The byte-pin was never their regression net.

## Consequences

- `main.mts` is the one file with no unit suite — by ADR-0002 it is an unimported
  wiring script whose logic lives in the tested helpers. Its render is now
  guarded by the rendered-typecheck, the existing targeted `toContain` assertions
  (the `GH_TOKEN` drop, the derived `.venv`/check-command lines), and PR-diff
  review. A silent rewrite that still typechecks is no longer caught by a test —
  accepted, because that is exactly the low-yield drift the byte-pin traded on. A
  one-time audit of the old `main.mts` prose declarations promoted any genuine
  contract string into the allowlist before the pin was deleted.
- The `PRE_ARC` pin and its git-archive stay — the copier-update backward-compat
  tests still install an adopter at that commit to prove an update from before the
  LANGUAGE arc round-trips. Only the pre-arc *render* half and the byte machinery
  left.
- The autonomous orchestrator relies on this suite to verify its own template
  renders. Its replacement safety net is the set-nets + contract strings +
  rendered-typecheck + human PR-diff review.
