# Machine load

Read before launching a solver, hunt, search or any multi-core job. Moved
here from sudokumaker-custom-constraints' `AGENTS.md` when its finders left
for `caneff/grid-hunts` (that repo's #748), so one copy serves every repo.

- **One hunt at a time, and `--workers 1` unless told otherwise.** This box is
  a WSL2 VM other agents share; oversubscribing it has hung the desktop. Check
  `uptime` before launching anything, and never let the total worker count
  approach the core count: leave most of the cores for everyone else. The one
  exception is a driver that guards the box itself. grid-hunts'
  `finders/hunt/` driver is one: its own `--workers` flag defaults to 3 and it
  refuses to start above a 1-minute load of 24 unless `--force-load` is given,
  so a hunt built on that protocol and launched with no `--workers` at all is
  already box-safe.
- Long runs go under `job-run --name <n>` and append to a progress file, so a
  kill does not lose the result.
- Reprioritise a running hunt with SIGSTOP/SIGCONT rather than kill, and sync
  found results into the repo on a timer so nothing is lost.
- Before a measurement run longer than a few minutes, state the expected wall
  clock and the decision the result changes. A result already on record (a
  prior DNF, a byte-equal baseline) is not re-measured. A refusal by a repo's
  standard driver is the recorded outcome: post it verbatim, never improvise
  a protocol to get a number.
- Before launching a long solver, search or hunt, list every available
  speedup (tighter model, channeling or decomposition, per-task splits,
  portfolio workers, warm starts, dropping constraints the goal does not
  need), apply the ones that pay and name the rest in the launch message.
  The fast approach should not wait for Chris to ask for it.
