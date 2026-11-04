#!/usr/bin/env python3
"""Spec #1634's landing: retire burndown once nothing running depends on it.

    python3 implement-spec/retire_landing.py check  --own-run <run-id>
    python3 implement-spec/retire_landing.py finish --own-run <run-id>

Run from the integration workspace. `check` goes before the integration PR's
merge. `finish` goes straight after it and before that workspace's cleanup:
the run's tools on `main` read the old cache until the merge lands, so moving
the cache earlier strands the run's own file. `finish` runs `check` first.

Exit 0: clear (`check`) or every step done (`finish`). Exit 1: refused, or a
step stopped; each line says which and why. Exit 2: a bad command line.

Alive means a `drain-<repo>` job alive under `job-run`, or a herdr pane whose
`name` is an agent a run file names, as a worker or as its controller, except
for `--own-run`. A finished run's file names agents too, so a pane left open
from one refuses until it is closed. Anything that cannot be read refuses:
"nothing is alive" is an answer only `job-run` and herdr can give
(`docs/agents/defect-classes.md`, class 1).

The script's removal ticket also removes `retire_landing_test.py` and the
exact-path exemption the zero-reference suite holds for this file.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

OLD_CACHE = ".cache/burndown"
NEW_CACHE = ".cache/spec-run"
JOBS_DIR = ".cache/agent-jobs"
# Always asked, whatever the jobs directory holds: with no `drain-*` directory
# there would otherwise be nothing to ask, and a missing `job-run` would pass.
THIS_REPOS_DRAIN = "drain-skills"
PROBE_TIMEOUT = 30
# `job-run --status`: exit code to the first word of its one line. An exit
# code without its word is not that answer (a wrapper exiting 0 having run
# nothing), so it reads as no answer.
ENDED = {0: "finished", 11: "killed", 12: "unknown"}
ALIVE = 10
SKILL_LINK = ".claude/skills/burndown"
RETIRED = "burndown"
ROOT = Path(__file__).resolve().parents[1]
AGENT_SKILLS = "caneff/agent-skills"
COMMIT_SUBJECT = "AGENTS.md: cite the spec run's hold, not the retired burn"
COMMIT_BODY = f"Part of {AGENT_SKILLS}#1634, which retired the burn."
# Well past this tracker's issue count. A listing that reaches it may be cut
# short, and the ticket looked for may be past the cut.
ISSUE_LIMIT = 5000
REMOVAL_TITLE = "Remove the burndown retirement's landing script"
REMOVAL_BODY = """## Parent

#1634

## TL;DR

The landing script has run and is dead code, so delete it.

## What to build

Delete `implement-spec/retire_landing.py` and
`implement-spec/retire_landing_test.py`, and remove the exact-path exemption
the zero-reference suite holds for the script.

## Acceptance criteria

- [ ] Neither file exists.
- [ ] The zero-reference suite has no exemption for the script and passes.
- [ ] `bash tests/all.sh --changed origin/main` passes.

## Blocked by

- #1634

## Seams under test

- The zero-reference suite.
"""
# Each repo's `AGENTS.md`: (text as it stands, the wording that replaces it).
# After #1634 the include-closure declaration is read for `loop.py dispatch`'s
# hold on files in flight, and there is no clumper grouping tickets by it.
REPOS = {
    "sudokumaker-custom-constraints": [
        ("The burn clumper (`~/.agents/skills/implement-spec/closure.py`) reads this section\n"
         "to find which files",
         "`~/.agents/skills/implement-spec/closure.py` reads this section for the hold\n"
         "`loop.py dispatch` puts on files in flight, to find which files"),
        ("(reported by the clumper, never run by it)",
         "(reported by `closure.py`, never run by it)"),
    ],
    "sudokupad-art": [
        ("None — the clumper only reports it,", "None — `closure.py` only reports it,"),
        ("Read by `~/.agents/skills/implement-spec/closure.py`, not by agents. Without it, all\n"
         "11 slices of spec #301 landed in one 42-file clump (agent-skills #1478).",
         "Read by `~/.agents/skills/implement-spec/closure.py` for the hold `loop.py\n"
         "dispatch` puts on files in flight, not by agents. Without it, the hold has\n"
         "only the files each ticket names to go on, not what a change reaches."),
    ],
    "twitch-rules-scroller": [
        ("**Live e2e is batched: once per burn, on merged `main`, at run close**",
         "**Live e2e is batched: once per run, on merged `main`, at run close**"),
        ("This section exists so a\n"
         "burndown clumps by what a change actually reaches rather than by directory\n"
         "subtree — with the repo's root-level layout, the subtree fallback puts every\n"
         "candidate in one clump (measured 2026-09-20: 13 candidates, one clump).",
         "This section exists so a\n"
         "spec run's hold on files in flight (`loop.py dispatch`) goes by what a change\n"
         "actually reaches rather than only by the files a ticket names."),
    ],
}


class Refused(Exception):
    """A step that stops, or an answer that cannot be read. The text is the
    cause found."""


def run(*argv, timeout=PROBE_TIMEOUT, stdin=None):
    """(status, stdout, stderr). A command that could not start or did not
    finish is a failed one, status 127 or 124, never an exception."""
    try:
        done = subprocess.run(argv, text=True, capture_output=True, check=False,
                              timeout=timeout, input=stdin)
    except OSError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", f"no answer in {timeout}s"
    return done.returncode, done.stdout, done.stderr


def live_drains():
    """Every `drain-*` job `job-run` says is alive."""
    jobs = Path.home() / JOBS_DIR
    if not jobs.is_dir():
        raise Refused(f"cannot read job-run: no directory at {jobs}")
    names = {p.name for p in jobs.glob("drain-*")} | {THIS_REPOS_DRAIN}
    alive = []
    for name in sorted(names):
        status, out, err = run("job-run", "--status", name)
        words = out.split()
        if status == ALIVE:
            alive.append(name)
        elif status not in ENDED or words[:1] != [ENDED[status]]:
            raise Refused(f"cannot read job-run --status {name}: exit {status}: "
                          f"{(out + err).strip() or 'no output'}")
    return alive


def pane_names():
    """The `name` of every pane herdr lists. A listing of no agents at all is
    refused too: this script runs beside its own run's panes, so an empty
    answer says herdr's registry is not what it looks like."""
    status, out, err = run("herdr", "agent", "list")
    if status != 0:
        raise Refused(f"cannot read herdr agent list: exit {status}: "
                      f"{(out + err).strip() or 'no output'}")
    try:
        agents = json.loads(out)["result"]["agents"]
    except (ValueError, KeyError, TypeError) as exc:
        raise Refused(f"cannot read herdr agent list: {exc!r} in its answer") from exc
    if not isinstance(agents, list) or not agents \
            or not all(isinstance(a, dict) for a in agents):
        raise Refused(f"cannot read herdr agent list: agents is {agents!r}")
    return {a["name"] for a in agents if a.get("name")}


def run_agents():
    """{run id: the agents its run file names}, from both cache directories:
    a re-run of `finish` meets the files at the new path. A JSON file with no
    `clumps` key is some other cache record, not a run."""
    runs = {}
    for cache in (OLD_CACHE, NEW_CACHE):
        for path in sorted((Path.home() / cache).glob("*.json")):
            try:
                body = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                raise Refused(f"cannot read run file {path}: {exc}") from exc
            if not isinstance(body, dict) or "clumps" not in body:
                continue
            try:
                agents = {clump["agent"] for clump in body["clumps"]}
            except (KeyError, TypeError) as exc:
                raise Refused(f"cannot read run file {path}: {exc!r} in its "
                              "clumps") from exc
            if body.get("controller"):
                agents.add(body["controller"])
            run_id = body.get("run_id", path.stem)
            runs[run_id] = runs.get(run_id, set()) | agents
    return runs


def alive_problems(own_run):
    """One line per reason not to land. Both sources are always asked, so a
    refusal names everything alive and not only the first thing found."""
    problems = []
    try:
        problems += [f"drain alive: job-run says {name} is alive"
                     for name in live_drains()]
    except Refused as exc:
        problems.append(str(exc))
    try:
        panes = pane_names()
        runs = run_agents()
        if own_run not in runs:
            problems.append(f"no run file names run {own_run}, so nothing here "
                            "knows which run to ignore")
        for run_id, agents in sorted(runs.items()):
            if run_id != own_run:
                problems += [f"spec run alive: run {run_id} names pane {name}"
                             for name in sorted(agents & panes)]
    except Refused as exc:
        problems.append(str(exc))
    return problems


def move_cache():
    """Rename the cache; once the new path exists, move what is at the old
    path across by name. Nothing is overwritten and nothing is deleted: a name
    at both paths stays at both and stops the step."""
    old, new = Path.home() / OLD_CACHE, Path.home() / NEW_CACHE
    if not old.exists():
        print(f"cache: already at {new}")
        return
    if not new.exists():
        old.rename(new)
        print(f"cache: moved to {new}")
        return
    conflicts = []
    for entry in sorted(old.iterdir()):
        if (new / entry.name).exists():
            conflicts.append(entry.name)
        else:
            entry.rename(new / entry.name)
    if conflicts:
        raise Refused(f"cache: {', '.join(conflicts)} exist at both {old} and "
                      f"{new}; both copies kept, a person chooses")
    old.rmdir()
    print(f"cache: moved what remained at {old} to {new}")


def dispatch_reads_new_cache():
    """Whether the installed binary's own help names the new cache. Exit 0
    from the installer says a build ran, not that it built the renamed tree."""
    binary = Path.home() / ".local/bin/implement-dispatch"
    _, out, err = run(str(binary), "--help")
    return NEW_CACHE in out + err


def rebuild_dispatch():
    if dispatch_reads_new_cache():
        print("implement-dispatch: already reads the new cache")
        return
    status, out, err = run("bash", str(ROOT / "flow/lane-install.sh"), timeout=None)
    if status != 0:
        raise Refused(f"flow/lane-install.sh exited {status}: "
                      f"{(out + err).strip()[-500:] or 'no output'}")
    if not dispatch_reads_new_cache():
        raise Refused("flow/lane-install.sh succeeded, but implement-dispatch "
                      f"--help does not name {NEW_CACHE}: {ROOT} holds no cache "
                      "rename")
    print("implement-dispatch: rebuilt")


def remove_skill_link():
    link = Path.home() / SKILL_LINK
    if link.is_symlink():
        link.unlink()
        print(f"skill link: removed {link}")
    elif link.exists():
        raise Refused(f"{link} is not a symlink; left for a person")
    else:
        print(f"skill link: {link} already gone")


def git(path, *args):
    """A git command's stdout, or a `Refused` carrying what git said."""
    status, out, err = run("git", "-C", str(path), *args, timeout=300)
    if status != 0:
        raise Refused(f"git {args[0]} failed: {(err + out).strip() or f'exit {status}'}")
    return out


def pending(text, edits):
    """The carried replacements this text has not had yet."""
    return [edit for edit in edits if edit[0] in text]


def reword(text, edits):
    for old, new in edits:
        text = text.replace(old, new)
    return text


def fix_repo(repo, edits):
    """One commit on `main`, pushed. Origin says whether it is owed, so a
    fix already landed is done whatever state the checkout has moved on to.
    An unpushed commit of ours is pushed, not remade, and our own wording left
    uncommitted by a failed commit is committed, not read as a dirty tree."""
    path = Path.home() / "src" / repo
    git(path, "fetch", "-q", "origin", "main")
    landed = git(path, "show", "origin/main:AGENTS.md")
    if not pending(landed, edits):
        if RETIRED in landed.lower():
            raise Refused(f"AGENTS.md on origin/main says {RETIRED} in text this "
                          "script does not carry; a person words it")
        print(f"{repo}: already landed")
        return
    branch = git(path, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != "main":
        raise Refused(f"on branch {branch}, not main")
    unpushed = git(path, "log", "--format=%s", "origin/main..HEAD").splitlines()
    foreign = [subject for subject in unpushed if subject != COMMIT_SUBJECT]
    if foreign:
        raise Refused(f"unpushed commits that are not this script's: {foreign}")
    if not unpushed:
        commit_rewording(path, edits)
    git(path, "push", "-q", "origin", "main")
    print(f"{repo}: committed and pushed")


def commit_rewording(path, edits):
    target = path / "AGENTS.md"
    head = git(path, "show", "HEAD:AGENTS.md")
    dirty = git(path, "status", "--porcelain").splitlines()
    ours = target.is_file() and target.read_text() == reword(head, edits) \
        and all(line[3:] == "AGENTS.md" for line in dirty)
    if dirty and not ours:
        raise Refused(f"dirty checkout: {'; '.join(dirty)}")
    if not dirty:
        git(path, "merge", "-q", "--ff-only", "origin/main")
        target.write_text(reword(git(path, "show", "HEAD:AGENTS.md"), edits))
    git(path, "add", "AGENTS.md")
    git(path, "commit", "-q", "-m", COMMIT_SUBJECT, "-m", COMMIT_BODY)


def file_removal_ticket():
    """Once ever: a ticket of this exact title in any state counts. The plain
    listing, not `--search`, whose index can lag behind a ticket just filed."""
    status, out, err = run("gh", "issue", "list", "--repo", AGENT_SKILLS,
                           "--state", "all", "--limit", str(ISSUE_LIMIT),
                           "--json", "number,title", timeout=300)
    if status != 0:
        raise Refused(f"gh issue list exited {status}: {(err + out).strip() or 'no output'}")
    try:
        filed = [i["number"] for i in json.loads(out) if i["title"] == REMOVAL_TITLE]
        listed = len(json.loads(out))
    except (ValueError, KeyError, TypeError) as exc:
        raise Refused(f"gh issue list answered something unusable: {exc!r}") from exc
    if filed:
        print(f"removal ticket: already filed as #{filed[0]}")
        return
    if listed >= ISSUE_LIMIT:
        raise Refused(f"gh issue list reached its limit of {ISSUE_LIMIT}, so the "
                      "ticket may exist past the cut")
    status, out, err = run("gh", "issue", "create", "--repo", AGENT_SKILLS,
                           "--title", REMOVAL_TITLE, "--label", "ready-for-agent",
                           "--body-file", "-", stdin=REMOVAL_BODY, timeout=120)
    if status != 0:
        raise Refused(f"gh issue create exited {status}: {(err + out).strip() or 'no output'}")
    if not re.search(r"/issues/\d+", out):
        raise Refused(f"gh issue create printed no issue URL: {out.strip() or 'no output'}")
    print(f"removal ticket: filed {out.strip()}")


def word_is_gone():
    """The last step. `rg` exits 1 only when it read every file and matched
    nothing; a file it could not read is exit 2, so it fails here too."""
    files = [str(Path.home() / "src" / repo / "AGENTS.md") for repo in REPOS]
    status, out, err = run("rg", "-i", "-n", RETIRED, *files)
    if status == 0:
        raise Refused(f"rg still finds {RETIRED}:\n{out.strip()}")
    if status != 1:
        raise Refused(f"rg exited {status}: {(err + out).strip() or 'no output'}")
    print("rg: the word is gone from all three AGENTS.md files")


def finish(own_run):
    """The moves in order, stopping at the first that fails. A repo's failure
    stops that repo's step only, and the last step still reports."""
    if check(own_run) != 0:
        return 1
    try:
        move_cache()
        rebuild_dispatch()
        remove_skill_link()
    except (Refused, OSError) as exc:
        print(f"stopped: {exc}")
        return 1
    steps = [(repo, lambda r=repo, e=edits: fix_repo(r, e))
             for repo, edits in REPOS.items()]
    steps += [("removal ticket", file_removal_ticket), ("last step", word_is_gone)]
    failed = False
    for name, step in steps:
        try:
            step()
        except (Refused, OSError) as exc:
            print(f"stopped: {name}: {exc}")
            failed = True
    return 1 if failed else 0


def check(own_run):
    problems = alive_problems(own_run)
    for problem in problems:
        print(f"refused: {problem}")
    if problems:
        return 1
    print(f"clear: no drain and no spec run alive, ignoring run {own_run}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Spec #1634's landing check and finish.")
    parser.add_argument("mode", choices=["check", "finish"])
    parser.add_argument("--own-run", required=True,
                        help="this retirement's run id, the one run ignored")
    args = parser.parse_args()
    return check(args.own_run) if args.mode == "check" else finish(args.own_run)


if __name__ == "__main__":
    sys.exit(main())
