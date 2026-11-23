#!/usr/bin/env python3
"""PROTOTYPE for #1628 -- throwaway, never merge to main.

Question: what fixed report shape should a bare `stat` give?
Three structurally different shapes over the same live sources:

  A  dashboard   -- one section per source, everything listed
  B  verdict     -- one headline line, then only what needs Chris
  C  ledger      -- one table, one row per live unit (worker, job, PR), all repos

Run:  python3 flow/bin/stat_PROTOTYPE.py --variant A|B|C [--repo PATH]
      python3 flow/bin/stat_PROTOTYPE.py --all      (prints all three)
"""
import argparse, json, os, subprocess, time
from pathlib import Path

JOBS = Path.home() / ".cache/agent-jobs"


def sh(*cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def age(seconds):
    s = int(seconds)
    return f"{s//86400}d" if s >= 86400 else f"{s//3600}h" if s >= 3600 else f"{s//60}m"


def gather(repo):
    repo = Path(sh("git", "rev-parse", "--show-toplevel", cwd=repo) or repo)
    common = Path(sh("git", "rev-parse", "--path-format=absolute", "--git-common-dir", cwd=repo)).parent
    name = common.name
    sh("git", "fetch", "-q", "origin", cwd=common)
    default = (sh("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=common) or "origin/main").split("/", 1)[1]
    counts = sh("git", "rev-list", "--left-right", "--count", f"{default}...origin/{default}", cwd=common) or "? ?"
    ahead, behind = counts.split()
    dirty = bool(sh("git", "status", "--porcelain", cwd=common))
    branch = sh("git", "branch", "--show-current", cwd=common)

    prs = json.loads(sh("gh", "pr", "list", "--json", "number,title,headRefName,isDraft,statusCheckRollup,updatedAt", cwd=common) or "[]")
    for p in prs:
        states = {(c.get("conclusion") or c.get("status") or "").upper() for c in p.pop("statusCheckRollup") or []}
        p["ci"] = "fail" if states & {"FAILURE", "CANCELLED", "TIMED_OUT"} else "run" if states & {"IN_PROGRESS", "QUEUED", "PENDING"} else "pass" if states else "none"

    counts_line = sh("issue-counts", "--status", cwd=common) or "(issue-counts failed)"

    panes = (json.loads(sh("herdr", "pane", "list") or '{"result":{"panes":[]}}')["result"]["panes"])
    workers, sessions = [], []
    for p in panes:
        cwd = p.get("cwd", "")
        row = {"pane": p["pane_id"], "status": p.get("agent_status", "?"), "title": p.get("terminal_title_stripped", ""), "cwd": cwd}
        (workers if "/worktrees/" in cwd else sessions).append(row)
        row["here"] = cwd.startswith(str(common))

    jobs = []
    if JOBS.is_dir():
        for d in JOBS.iterdir():
            if not (d / "pid").exists() or (d / "exit").exists():
                continue
            try:
                os.kill(int((d / "pid").read_text().strip()), 0)
            except (ValueError, ProcessLookupError, PermissionError):
                continue
            prog = d / "progress"
            last = prog.read_text(errors="replace").strip().splitlines()[-1:] if prog.exists() else []
            jobs.append({"name": d.name, "age": age(time.time() - (d / "pid").stat().st_mtime),
                         "quiet": age(time.time() - prog.stat().st_mtime) if prog.exists() else "?",
                         "last": (last[0] if last else "")[:70]})

    return dict(common=str(common), name=name, default=default, ahead=int(ahead) if ahead.isdigit() else ahead,
                behind=int(behind) if behind.isdigit() else behind, dirty=dirty, branch=branch,
                prs=prs, counts=counts_line, workers=workers, sessions=sessions, jobs=jobs)


def variant_a(s):
    print(f"== {s['name']}  ({s['branch']}{', dirty' if s['dirty'] else ''})")
    print(f"\n-- main vs origin\n   {s['default']}: {s['ahead']} ahead, {s['behind']} behind origin/{s['default']}")
    print(f"\n-- tickets\n   {s['counts']}")
    print(f"\n-- open PRs ({len(s['prs'])})")
    for p in s["prs"]:
        print(f"   #{p['number']:<5} ci:{p['ci']:<5} {'draft ' if p['isDraft'] else ''}{p['title'][:60]}")
    here = [w for w in s["workers"] if w["here"]]
    print(f"\n-- workers in this repo ({len(here)})")
    for w in here:
        print(f"   {w['pane']:<9} {w['status']:<8} {w['title'][:50]}  [{Path(w['cwd']).name}]")
    print(f"\n-- live job-run jobs, all repos ({len(s['jobs'])})")
    for j in s["jobs"]:
        print(f"   {j['name'][:40]:<40} up {j['age']:>4}  quiet {j['quiet']:>4}  {j['last'][:40]}")


def variant_b(s):
    here = [w for w in s["workers"] if w["here"]]
    busy = [w for w in here if w["status"] == "working"]
    stuck_workers = [w for w in here if w["status"] in ("done", "idle", "unknown")]
    failing = [p for p in s["prs"] if p["ci"] == "fail"]
    quiet_jobs = [j for j in s["jobs"] if j["quiet"].endswith(("h", "d"))]
    sync = "main in sync" if s["ahead"] == 0 and s["behind"] == 0 else f"main {s['ahead']}↑ {s['behind']}↓"
    print(f"{s['name']}: {len(busy)} worker(s) busy, {len(s['prs'])} PR(s) open, {len(s['jobs'])} job(s) live, {sync}.")
    needs = []
    if s["behind"]:
        needs.append(f"primary checkout is {s['behind']} behind -> git -C {s['common']} pull --ff-only")
    if s["dirty"]:
        needs.append("primary checkout is dirty")
    needs += [f"PR #{p['number']} CI failing: {p['title'][:50]}" for p in failing]
    needs += [f"worker {w['pane']} {w['status']}, not working: {w['title'][:45]}" for w in stuck_workers]
    needs += [f"job {j['name'][:35]} silent for {j['quiet']}" for j in quiet_jobs]
    if needs:
        print("needs you:")
        for n in needs:
            print(f"  - {n}")
    else:
        print("nothing needs you.")
    print(f"tickets: {s['counts']}")


def variant_c(s):
    rows = []
    for w in s["workers"]:
        rows.append(("worker", (Path(w["cwd"]).parts[-4] if Path(w["cwd"]).parts[-3] == ".claude" else Path(w["cwd"]).parts[-2]), w["status"], Path(w["cwd"]).name, w["title"][:40]))
    for j in s["jobs"]:
        rows.append(("job", "", f"quiet {j['quiet']}", j["name"][:28], j["last"][:40]))
    for p in s["prs"]:
        rows.append(("pr", s["name"], f"ci {p['ci']}", f"#{p['number']}", p["title"][:40]))
    rows.append(("main", s["name"], f"{s['ahead']}↑ {s['behind']}↓", s["default"], "dirty" if s["dirty"] else "clean"))
    hdr = ("KIND", "REPO", "STATE", "WHAT", "DETAIL")
    w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(5)]
    for r in [hdr] + sorted(rows, key=lambda r: (r[0], r[1])):
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)).rstrip())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="A", choices="ABC")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    s = gather(a.repo)
    for v in ("ABC" if a.all else a.variant):
        if a.all:
            print(f"\n################ variant {v} ################")
        {"A": variant_a, "B": variant_b, "C": variant_c}[v](s)
