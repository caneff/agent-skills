# The run file: one run's state, and what a resume reads

A run's state lives in **one JSON file per run**, at
`~/.cache/burndown/<run-id>.json`, read and written by `burndown/runfile.py`.
It is the only place a run's state lives: the controller's context is not
state, and a per-repo log is not this run.

```
python3 burndown/runfile.py start  <run-id> --slots <k> [--controller <agent>]
python3 burndown/runfile.py clump  <run-id> --tickets 901,902 --workspace <path> --agent <name>
python3 burndown/runfile.py job    <run-id> --clump 901 --cores 8 | --none | --done
python3 burndown/runfile.py land   <run-id> --clump 901 --sha <sha>
python3 burndown/runfile.py show   <run-id>
python3 burndown/runfile.py resume <run-id> --live a,b [--controller <agent>]
```

## What it holds

```json
{
  "run_id": "burn-2026-09-20-0905",
  "slots": 3,
  "controller": "burn-ctl-1a",
  "clumps": [
    {"tickets": [901, 902], "workspace": "/home/c/src/x/.claude/worktrees/implement-901",
     "agent": "implement-901-42", "job": {"state": "running", "cores": 8},
     "landed": null},
    {"tickets": [905], "workspace": "/home/c/src/x/.claude/worktrees/implement-905",
     "agent": "implement-905-7", "job": {"state": "none", "cores": 0},
     "landed": "0123456789abcdef0123456789abcdef01234567"}
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
  landing frees a slot for certain.
- **The controller** is the controller's own **herdr agent name**, rewritten
  by `resume --controller <name>` on every resume.
- **A clump** is keyed by its **lowest ticket** — the same number its branch
  and its workspace are named for. Registering the same lowest again moves the
  workspace and the agent and keeps the landing sha, and it may **grow** the
  clump — a closure re-resolve that adds a ticket — but never drop one out of
  the run: this file is what answers "which tickets are out". A ticket that
  already sits in *another* clump is refused too, because one ticket in two
  clumps is two workers in the same files.
- **A ticket list** is digits: `901,902` or `901 902`. `9_01` and `+901` are
  refused rather than read as 901.
- **`landed`** is the clump's squash sha, or `null`. It must be a git object
  name, and once written a *different* sha is refused: the squash sha is
  final, so a second one is a stale writer rather than a correction.


## The job record

Each clump carries what parallel job its worker has out: `null` when nothing
is on record, `{"state": "running", "cores": <n>}` while a job is out,
`{"state": "none", "cores": 0}` when the worker declared it launched none, and
`{"state": "done", "cores": 0}` once it reports the job finished.
`runfile.py job <run-id> --clump <n> --cores <k> | --none | --done` writes it.

Three states and not a bare number, because `null` and `none` are different
facts: a worker nobody recorded and a worker that declared nothing read alike
to a controller charging cores, and charging the first as the second is the
dispatch into a loaded box that #894 exists to stop. A file written before
this field existed still loads — the field is filled in as `null`, which is
the honest reading of a run that never recorded one.


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
and splits the clumps three ways against the agents that are alive:

```
run burn-2026-09-20-0905  slots 3  held 2  free 1  controller burn-ctl-f3
re-announce  implement-901-42  #901,#902  /home/c/src/x/.claude/worktrees/implement-901
vanished     implement-903-9   #903       /home/c/src/x/.claude/worktrees/implement-903
landed       0123456789abcdef0123456789abcdef01234567  #905
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
   is [#923](https://github.com/caneff/agent-skills/issues/923). Nothing
   re-announces today because nothing runs a burn today: this skill is parked.
3. **`vanished`** is a clump the run started and cannot reach. It is not a
   landing, and its slot is **not free**: `held` counts it, because its worker
   may still be holding those tickets. The controller reads the workspace,
   decides whether the work is there, and either re-dispatches (`clump` again,
   with the new workspace and agent) or parks it — and the slot frees when the
   clump lands.
4. **A landed clump is in neither working bucket**, however its agent looks —
   its sha is banked and re-announcing to a finished worker is noise.

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
