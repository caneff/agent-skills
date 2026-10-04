# The run file: one run's state, and what a resume reads

A run's state lives in **one JSON file per run**, at
`~/.cache/burndown/<run-id>.json`, read and written by `burndown/runfile.py`.
It is the only place a run's state lives: the controller's context is not
state, and a per-repo log is not this run.

```
python3 burndown/runfile.py start    <run-id> --repo <checkout> [--slots <k>] [--controller <agent>]
python3 burndown/runfile.py clump    <run-id> --tickets 901,902 --workspace <path> --agent <name>
python3 burndown/runfile.py job      <run-id> --clump 901 --cores 8 | --none | --done
python3 burndown/runfile.py land     <run-id> --clump 901 --sha <sha>
python3 burndown/runfile.py close    <run-id> --clump 901 --reason <text>
python3 burndown/runfile.py pr-up    <run-id> --clump 901 --pr 950 | --clear
python3 burndown/runfile.py show     <run-id>
python3 burndown/runfile.py resume   <run-id> --live a,b [--controller <agent>]
```

## What it holds

```json
{
  "run_id": "burn-2026-09-20-0905",
  "slots": 3,
  "controller": "burn-ctl-1a",
  "repo": "/home/c/src/x",
  "clumps": [
    {"tickets": [901, 902], "workspace": "/home/c/src/x/.claude/worktrees/implement-901",
     "agent": "implement-901-42", "job": {"state": "running", "cores": 8},
     "pr_up": null, "landed": null, "closed": null},
    {"tickets": [905], "workspace": "/home/c/src/x/.claude/worktrees/implement-905",
     "agent": "implement-905-7", "job": {"state": "none", "cores": 0},
     "pr_up": 950,
     "landed": "0123456789abcdef0123456789abcdef01234567", "closed": null}
  ]
}
```

- **The run id** names the file, so it is letters, digits, dash, dot and
  underscore — a `/` or a `..` would write the state outside the cache dir.
- **The slot budget** is what a resumed controller refills against. `resume`
  reports `held` — the live workers **and** the vanished ones — and `free` as
  the budget minus that, so a controller that comes back does not have to count
  panes to know what it may dispatch. A vanished clump holds its slot until
  someone reconciles it: its worker may still be in those files, and only a
  landing or a close frees a slot for certain.
- **The controller** is the controller's own **herdr agent name**, rewritten
  by `resume --controller <name>` on every resume.
- **A clump** is keyed by its **lowest ticket** — the same number its branch
  and its workspace are named for. Registering the same lowest again moves the
  workspace and the agent, keeps the landing sha and reopens a closed clump
  (it has a worker again), and it may **grow** the
  clump — a closure re-resolve that adds a ticket — but never drop one out of
  the run: this file is what answers "which tickets are out". A ticket that
  already sits in *another* clump is refused too, because one ticket in two
  clumps is two workers in the same files.
- **A ticket list** is digits: `901,902` or `901 902`. `9_01` and `+901` are
  refused rather than read as 901.
- **`landed`** is the clump's squash sha, or `null`. It must be a git object
  name, and once written a *different* sha is refused: the squash sha is
  final, so a second one is a stale writer rather than a correction.
- **`closed`** is the one-line reason a clump finished with **no landing of
  its own**, or `null` (#1310): its ticket was found already fixed on the
  default branch, or it was handed to a nested spec run whose landings live in
  that run's own file. A nested run's clump is closed once that run has
  finished, never at the hand-off: a closed clump's files are free to this
  run's dispatch, which never reads the nested run's file, so closing early
  dispatches into files its workers are still editing. `runfile.py close <run-id> --clump <n> --reason <text>`
  writes it. A clump is landed or closed, never both: `close` refuses a landed
  clump and `land` a closed one. Recording `main`'s tip as a landing instead is
  a sha with no PR behind it, and `counts.py` then refuses the run over
  the sidecar that PR never wrote. A closed clump holds no slot, gets no
  re-announce, is no live workspace to `loop.py dispatch` or its liveness
  sweep, and `counts.py` names it as skipped. A file written before this
  field existed loads with it as `null`.


## The job record

Each clump carries what parallel job its worker has out: `{"state": "none",
"cores": 0}` from `runfile.py clump` on, since a worker starts with nothing out
(#1311); `{"state": "running", "cores": <n>}` while a job is out; the same
`none` record when the worker declared it launched none; and
`{"state": "done", "cores": 0}` once it reports the job finished. `null` means
nothing on record and appears only in a file written before jobs existed.
`runfile.py job <run-id> --clump <n> --cores <k> | --none | --done` writes it.
The worker writes it before launching its job (#1339), and who writes it when
that is refused is `burndown/SKILL.md` § Liveness.

Three states and not a bare number. `null` and `none` are different facts: a
worker nobody recorded and a worker that declared nothing read alike to a
controller charging cores, and charging the first as the second is the
dispatch into a loaded box that #894 exists to stop. #1311 accepts that
trade for a clump just registered: the `none` `runfile.py clump` writes reads
the same as a declared one, because a controller that waited for the worker's
first word idled every free slot for the hour before its "PR up". A file
written before this field existed still loads with `null`, the honest reading
of a run that never recorded one, and is still refused.


## The PR-up record

Each clump carries `pr_up`: the PR number its worker's "PR up" named, or
`null` until one reaches the controller. `runfile.py pr-up <run-id> --clump
<n> --pr <n>` writes it, when the controller reads that message, and `--clear`
resets it to `null` when the controller hands findings back: the PR stays
open through a fix round, and only the clear lets a worker that stops
mid-fix read `stalled` again. The sweep
reads it, and what it reads it for is `burndown/SKILL.md` § Liveness. A file
written before this field existed loads with it as `null`, which reads a
finished pane as `stalled`: the loud reading, and the controller's read of
the pane settles it.

## Dispositions and counts

The run file holds no review findings: a worker fixes every valid finding in
its own PR (`implement/SKILL.md` § Review), so nothing is carried from a
landed PR into the run. What a landed PR records is its dispositions sidecar,
`dispositions-<n>.jsonl` in the review cache, one line per finding with the
outcome `fixed` (a sha), `moved` (the open ticket it was added to) or
`disputed` (a reason). `implement/fix-check.sh` checks it before the PR
merges.

`counts.py <run-id> --repo <checkout>` reads each landed clump's sidecar
through `runfile.read_dispositions` and prints the closing report's two
counts, fixed and moved. `read_dispositions` refuses by file and line a line
that is not a JSON object, whose `outcome` is none of the three, or with no
`id`, and a second line carrying an id an earlier line already has (#1124):
reading any of them as "skip" would report a low count with a clean exit,
indistinguishable from a PR that genuinely had nothing to fix. A landed clump
with no sidecar is refused by clump number, never counted as zero: the worker
writes the sidecar even when its reviewers found nothing.

A burn that was running when #1401 landed has sidecars in the old vocabulary.
`counts.py` reads them (`legacy=True`): `filed` counts as moved, and
`leftover` and `handed-back` are printed as a count that nothing sweeps, since
the sweep is gone; the run file's own `leftovers` list is ignored by this code
and left in the file. The merge check never accepts those outcomes.

## Why `~/.cache/burndown/<run-id>.json`

**Per run, not per repo.** The retired `~/.cache/burndown/<repo>.progress` was
an append-only prose log for a whole repo. On #781 it already held five
earlier burns, each ending in `done`, before that run appended its first line
— so "is this run finished" and "which tickets are out" were questions a
reader answered by finding where the run started, by eye. Nothing reads that
file now, and nothing should write one.

**`~/.cache`, not `/tmp` and not a session scratchpad.** A WSL restart wipes
both, and a restart is the event this file exists for. It is also not repo
content: the workers branch from the target tree, and the controller may be
driving a repo it is not sitting on.

**Machine-readable.** Resume, the liveness sweep and the run's closing report
all read the same file, so none of them re-derives the run from prose.

## Addressing: the herdr agent name

A worker is addressed by its **herdr agent name**, in the brief and in the run
file. A Claude session name does not survive a restart: on #781 a WSL restart
at 09:14 renamed the controller from `spectest-1a` to `spectest-f3` and a
worker from `implement-368-42` to `implement-368-50`, and every worker's brief
hard-codes `--controller "<name>"` — so the next report would have gone to an
address that no longer existed. The herdr agent name was the only stable
handle, and it is the one recorded here.

## Resume

`resume <run-id> --live <names> --controller <my agent name>` reads the file
and splits the clumps four ways against the agents that are alive:

```
run burn-2026-09-20-0905  slots 3  held 2  free 1  controller burn-ctl-f3
re-announce  implement-901-42  #901,#902  /home/c/src/x/.claude/worktrees/implement-901
vanished     implement-903-9   #903       /home/c/src/x/.claude/worktrees/implement-903
landed       0123456789abcdef0123456789abcdef01234567  #905
closed       #907  duplicate of #880, already fixed on main
```

1. **The live names come from the machine**, never from the file and never
   from a terminal tail: `herdr agent get` over the recorded agent names, the
   sessions registry. The file says who the run started; only the box says who
   is still there.
2. **`re-announce`** is the work, and it is the **controller's** to do:
   `resume` names who to send to and sends nothing itself, because sending is
   `SendMessage` and a Python module cannot perform it. The controller sends
   each live worker its own current address, because that worker's brief
   carries the name the restart invalidated — a worker whose controller
   address is dead reports into nothing, and the run loses its fan-in
   silently. The loop that performs it is
   [#893](https://github.com/caneff/agent-skills/issues/893); resolving each
   herdr agent name to a current address — it cannot be stored, only resolved —
   is `resolve-controller <herdr agent name>` (#923), whose two-hop mechanism
   is stated once, in `implement/SKILL.md` § Control. The controller resolves
   each worker's agent name with it before the send.
3. **`vanished`** is a clump the run started and cannot reach. It is not a
   landing, and its slot is **not free**: `held` counts it, because its worker
   may still be holding those tickets. The controller reads the workspace,
   decides whether the work is there, and either re-dispatches (`clump` again,
   with the new workspace and agent) or parks it — and the slot frees when the
   clump lands.
4. **A landed clump is in neither working bucket**, however its agent looks —
   its sha is banked and re-announcing to a finished worker is noise. **A
   closed clump** is in neither either, and is listed with its reason.

## Writing

Every command that changes the file holds an advisory `flock` on
`<run-id>.json.lock` across its read-modify-replace — the same lock the
dispatch lane waits on, with the same 30-second ceiling before it refuses
(`BURNDOWN_RUNFILE_LOCK_TIMEOUT` moves it). The lock sits beside the run file
rather than on it, because `start` takes the lock before the run file exists.

Without it, two commands racing both read and both replace, and the second
writes back a run that never saw the first: a landing's sha overwritten by a
stale `landed: null`, and a resumed controller re-dispatching work that already
landed with a merged PR behind it. One controller per run is still the lane's
rule; the lock is what makes it true rather than assumed.

Each write goes to a temp file beside the target, is flushed to disk, and is
moved over the target with `os.replace`: a reader — including a resume after a
crash — sees the old file or the new one, never a half-written one that would
read as a run with no clumps. The directory sync that follows is best effort,
because by then the write has landed and reporting it as failed would send the
controller back to a `start` that now refuses.

A write that fails leaves the previous state in place and says so on stderr
with a nonzero exit. Every refusal here is one stderr line, never a traceback,
including the ones a restart brings: a `$HOME` that is full or read-only, a
file where the cache dir belongs, a lock another writer is holding, and a run
file this module does not recognise. `load` checks every field, not just the
keys — the run id against the filename it came from, the slot budget as a
positive count, the controller and each clump's workspace and agent as
non-blank names, each ticket as a positive number, each landing as a git object
name — because a `slots` that is a string reaches arithmetic in `resume` two
calls later, and a controller recovering from a restart needs the diagnostic
rather than the traceback.

`BURNDOWN_CACHE_DIR` moves the whole directory, which is how the tests stay
off the real one. The CLI resolves it once and passes it down; an in-process
caller passes `root` instead.

Every environment read goes through one guarded conversion, so a value
inherited from a parent shell is a refusal and not a traceback: unset or empty
means the documented default (`VAR=` is the shell's own way to clear an
override), and anything that is not a non-negative finite number — `30s`,
`inf`, `nan`, `-5` — is refused by name. `inf` would wait forever and `nan`
compares false against every deadline, which is the same wait without a name.
