# The run file: one run's state, and what a resume reads

A run's state lives in **one JSON file per run**, at
`~/.cache/burndown/<run-id>.json`, read and written by `burndown/runfile.py`.
It is the only place a run's state lives: the controller's context is not
state, and a per-repo log is not this run.

```
python3 burndown/runfile.py start  <run-id> --slots <k> [--controller <agent>]
python3 burndown/runfile.py clump  <run-id> --tickets 901,902 --workspace <path> --agent <name>
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
     "agent": "implement-901-42", "landed": null},
    {"tickets": [905], "workspace": "/home/c/src/x/.claude/worktrees/implement-905",
     "agent": "implement-905-7", "landed": "0123456789abcdef0123456789abcdef01234567"}
  ]
}
```

- **The run id** names the file, so it is letters, digits, dash, dot and
  underscore — a `/` or a `..` would write the state outside the cache dir.
- **The slot budget** is what a resumed controller refills against. `resume`
  reports `free` as the budget minus the live workers, so a controller that
  comes back does not have to count panes to know what it may dispatch.
- **The controller** is the controller's own **herdr agent name**, rewritten
  by `resume --controller <name>` on every resume.
- **A clump** is keyed by its **lowest ticket** — the same number its branch
  and its workspace are named for. Registering the same lowest again moves the
  workspace and the agent and keeps the landing sha; a ticket that already
  sits in another clump is refused, because one ticket in two clumps is two
  workers in the same files.
- **`landed`** is the clump's squash sha, or `null`. It must be a git object
  name, and once written a *different* sha is refused: the squash sha is
  final, so a second one is a stale writer rather than a correction.

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
run burn-2026-09-20-0905  slots 3  free 2  controller burn-ctl-f3
re-announce  implement-901-42  #901,#902  /home/c/src/x/.claude/worktrees/implement-901
vanished     implement-903-9   #903       /home/c/src/x/.claude/worktrees/implement-903
landed       0123456789abcdef0123456789abcdef01234567  #905
```

1. **The live names come from the machine**, never from the file and never
   from a terminal tail: `herdr agent get` over the recorded agent names, the
   sessions registry. The file says who the run started; only the box says who
   is still there.
2. **`re-announce`** is the work: the controller sends each live worker its
   own current address, because that worker's brief carries the name the
   restart invalidated. A worker whose controller address is dead reports into
   nothing, and the run loses its fan-in silently.
3. **`vanished`** is a clump the run started and cannot reach. It is not a
   landing and not a free slot's worth of nothing: the controller reads the
   workspace, decides whether the work is there, and either re-dispatches
   (`clump` again, with the new workspace and agent) or parks it.
4. **A landed clump is in neither working bucket**, however its agent looks —
   its sha is banked and re-announcing to a finished worker is noise.

## Writing

Only the controller writes, one command at a time, so there is no lock. Each
write goes to a temp file beside the target, is flushed to disk, and is moved
over the target with `os.replace`: a reader — including a resume after a crash
— sees the old file or the new one, never a half-written one that would read
as a run with no clumps. A write that fails leaves the previous state in place
and says so on stderr with a nonzero exit; every refusal in this module is one
stderr line, never a traceback.

`BURNDOWN_CACHE_DIR` moves the whole directory, which is how the tests stay
off the real one.
