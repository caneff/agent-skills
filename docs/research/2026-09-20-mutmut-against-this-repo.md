# What happens when you actually run mutmut here

2026-09-20. #962 said `mutation-audit` had never run because mutmut was not
installed. Chris approved installing it. This is what the run found.

## mutmut installs fine; it is the repo's layout that stops it

`uvx --with pytest mutmut run` fetches mutmut 3.x in about a second, so the
skill's own recipe never needed a global install and `which mutmut` being
empty was never the blocker. The blockers are three, in the order you hit
them.

**1. mutmut refuses to do anything, including `--help`, without
`source_paths`.** `mutmut --help` raises `FileNotFoundError: Could not figure
out where the code to mutate is` before argument parsing. So the tool looks
broken rather than unconfigured, which is why nobody got past it.

**2. mutmut copies `source_paths` into `mutants/` and runs pytest with
`--rootdir=.` inside that copy.** This repo puts a module and its test side
by side — `burndown/loop.py` and `burndown/loop_test.py` — with no package
directory and no `tests/` directory for them. Scope `source_paths` to the one
module the skill tells you to and the test file is not copied, so pytest
collects nothing and mutmut exits with `failed to collect stats. runner
returned 5`. Setting the `tests_dir` key does not help and is deprecated in
favour of `pytest_add_cli_args_test_selection`, which selects tests but does
not copy them. The combination that gets a suite running is
`source_paths=burndown/` — the whole directory — plus
`pytest_add_cli_args_test_selection=burndown/loop_test.py`, and a copy of
`setup.cfg` placed inside `mutants/` by hand, because mutmut does not copy
its own config into the tree it then runs from.

**3. The stopper: mutmut rewrites each source file to import mutmut, so a
test that runs that file as a subprocess dies.** With the above, pytest gets
as far as `1 failed, 42 passed` and the run aborts at stats collection.
The failure is `test_the_cli_refuses_a_seat_in_a_worktree_it_makes_itself`,
which shells out to `loop.py` from a temporary working directory. The
instrumented copy imports mutmut at module scope, mutmut loads its config
relative to the process's cwd, that cwd has no `setup.cfg`, and the
subprocess dies with the same `FileNotFoundError` as (1). Stats collection
runs pytest under `-x`, so one such test ends the run.

That is not a fixable config: any suite here that exercises a CLI by running
it as a subprocess will hit it, and `burndown/loop.py` is a CLI. The three
modules most worth mutating are the ones most likely to be tested this way.

## What this means for #961 and #962

#961 wants call-site mutation — delete the call to a guard and confirm the
entry point notices. mutmut would give that mechanically: an unreached line
is its `no-coverage` bucket, which `parse_mutmut_results` already handles.
That payoff is real and it is still out of reach for exactly the modules
where today's six findings lived.

So #962's three options stand, with the evidence sharpened. The honest
reading is that mutmut 3.x assumes a package plus a separate tests directory
and in-process tests, and this repo has neither. Either something bridges
that gap, or `mutation-audit` is parked and says so out loud, or the audit
reports "mutmut cannot run against this layout" as an explicit inconclusive
result. What it must never do is what it does now: pass its selfcheck as one
of the gate's 71 green suites while being unable to produce a single finding
about this repo.

## Reproducing

A detached worktree outside the checkout, `setup.cfg` as above, `uvx --with
pytest mutmut run`. The whole loop is about two minutes to the subprocess
failure. `mutants/` and `.mutmut-cache` are the artifacts to delete
afterwards.
