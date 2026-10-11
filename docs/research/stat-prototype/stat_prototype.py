#!/usr/bin/env python3
"""PROTOTYPE — throwaway, not production. Ticket #1039.

Question: what should a one-command `stat` print? Three structurally
different layouts of the same live data, picked with --variant:

  a  by kind       box line, then jobs / agents / waiting-on-you tables
  b  by workspace  one block per repo, its agents, jobs and PRs nested
  c  triage        what needs Chris first, running next, idle collapsed

Run:  python3 docs/research/stat-prototype/stat_prototype.py --variant a
      (--no-gh skips the GitHub calls; --all prints a, b and c in turn)

Read-only. Sources: `herdr agent list`, ~/.cache/agent-jobs (job-run's
records), burndown/loop.py's agent counter, `gh` per repo with a live agent.
Monitors are NOT shown: a Monitor lives inside its Claude session and leaves
nothing on disk for an outside command to read.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "burndown"))
import loop  # noqa: E402  burndown's counter, reused not copied

JOBS = Path.home() / ".cache/agent-jobs"
RECENT_S = 3600
HOME = str(Path.home())


def sh(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.stdout if r.returncode == 0 else ""


def short(path):
    return path.replace(HOME, "~") if path else "?"


def age(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"


def repo_root(path):
    """The main checkout a path belongs to, so worktrees group with it."""
    m = re.match(r"(.*?)/\.claude/worktrees/", path or "")
    if m and (Path(m.group(1)) / ".git").exists():
        return m.group(1)
    top = sh(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
             cwd=path if path and os.path.isdir(path) else None).strip()
    return str(Path(top).parent) if top else (path or "?")


def gather_agents():
    out = sh(["herdr", "agent", "list"])
    agents = json.loads(out)["result"]["agents"] if out else []
    rows = []
    for a in agents:
        cwd = a.get("cwd", "")
        m = re.search(r"/(implement|spec)-(\d+)$", cwd)
        rows.append({
            "status": a.get("agent_status", "?"),
            "cwd": cwd,
            "root": repo_root(cwd),
            "title": a.get("terminal_title_stripped", ""),
            "pane": a.get("pane_id", ""),
            "ticket": f"{m.group(1)} #{m.group(2)}" if m else "",
            "worker": bool(a.get("name")),
        })
    return rows


def gather_jobs():
    now = time.time()
    rows = []
    for d in JOBS.iterdir():
        pidf, exitf, prog = d / "pid", d / "exit", d / "progress"
        if not pidf.exists():
            continue
        started = pidf.stat().st_mtime
        ended = exitf.stat().st_mtime if exitf.exists() else None
        if ended and now - ended > RECENT_S:
            continue
        pid = pidf.read_text().strip()
        alive = pid.isdigit() and os.path.exists(f"/proc/{pid}")
        if not ended and not alive and now - started > RECENT_S:
            continue
        if ended:
            rec = dict(l.split("=", 1) for l in exitf.read_text().split())
            state = "ok" if rec.get("rc") == "0" else f"FAILED rc={rec.get('rc')}"
        else:
            state = "running" if alive else "KILLED (no exit record)"
        last, stale = "", None
        if prog.exists() and prog.stat().st_size:
            with open(prog, "rb") as f:
                f.seek(max(0, prog.stat().st_size - 4096))
                lines = f.read().decode(errors="replace").strip().splitlines()
            last = re.sub(r"^\S+Z ", "", lines[-1]) if lines else ""
            stale = now - prog.stat().st_mtime
        cmd = (d / "cmd").read_text().strip() if (d / "cmd").exists() else ""
        m = re.search(r"cd (\S+)", cmd)
        cwd = m.group(1) if m else ""
        if alive and not cwd:
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                pass
        rows.append({
            "name": d.name, "state": state, "alive": alive,
            "elapsed": (ended or now) - started, "last": last,
            "stale": stale if alive else None,
            "cwd": cwd, "root": repo_root(cwd) if cwd else "?",
        })
    return sorted(rows, key=lambda j: (not j["alive"], j["elapsed"]))


def gather_box(agents):
    count, counter, working, unlisted = loop.agent_count(
        SimpleNamespace(processes=None))
    live = sum(1 for a in agents if a["worker"] and a["status"] == "working")
    load = os.getloadavg()[0]
    return {"count": count, "counter": counter, "working": working,
            "unlisted": unlisted, "live": live, "load": load,
            "cap": loop.PROCESS_CAP}


def gather_gh(roots):
    def one(root):
        prs = sh(["gh", "pr", "list", "--json",
                  "number,title,isDraft,labels,headRefName"], cwd=root)
        issues = sh(["gh", "issue", "list", "--limit", "300", "--json",
                     "number,title,labels"], cwd=root)
        return root, json.loads(prs or "[]"), json.loads(issues or "[]")
    with ThreadPoolExecutor(8) as pool:
        return {r: (p, i) for r, p, i in pool.map(one, roots)}


def labels(item):
    return [l["name"] for l in item.get("labels", [])]


def label_counts(issues):
    counts = {}
    for i in issues:
        for name in labels(i) or ["(unlabelled)"]:
            counts[name] = counts.get(name, 0) + 1
    order = ["ready-for-human", "ready-for-agent", "needs-info", "backlog"]
    return "  ".join(f"{n} {counts[n]}" for n in order if n in counts)


def box_line(box):
    split = (f" ({box['working']} working, {box['unlisted']} unlisted)"
             if box["working"] is not None else "")
    return (f"BOX   {box['count']}/{box['cap']} agent processes{split}, "
            f"{box['live']} live workers, load {box['load']:.1f}")


def job_line(j, width=28):
    stale = (f"  [quiet {age(j['stale'])}]"
             if j["stale"] and j["stale"] > 300 else "")
    return (f"{j['name'][:width]:<{width}} {j['state']:<12} "
            f"{age(j['elapsed']):>6}  {j['last'][:60]}{stale}")


# --- variant a: by kind -----------------------------------------------------

def variant_a(box, agents, jobs, gh):
    print(box_line(box))
    print(f"\nJOBS  ({sum(j['alive'] for j in jobs)} running, "
          f"ended in the last hour shown)")
    for j in jobs:
        print("  " + job_line(j))
    print(f"\nAGENTS  ({len(agents)} panes)")
    for a in sorted(agents, key=lambda a: a["status"] != "working"):
        print(f"  {a['status']:<8} {a['pane']:<7} {a['ticket']:<15} "
              f"{short(a['cwd'])[-44:]:<44} {a['title'][:34]}")
    print("\nPRS")
    for root, (prs, _) in gh.items():
        for p in prs:
            print(f"  {Path(root).name[:24]:<24} #{p['number']:<5} "
                  f"{'draft ' if p['isDraft'] else ''}{p['title'][:60]}")
    print("\nTICKETS")
    for root, (_, issues) in gh.items():
        print(f"  {Path(root).name[:24]:<24} {len(issues):>3} open   "
              f"{label_counts(issues)}")
    print("\nWAITING ON YOU")
    for line in waiting(agents, jobs, gh):
        print("  " + line)


# --- variant b: by workspace ------------------------------------------------

def variant_b(box, agents, jobs, gh):
    print(box_line(box))
    roots = sorted({a["root"] for a in agents} | {j["root"] for j in jobs})
    for root in roots:
        mine_a = [a for a in agents if a["root"] == root]
        mine_j = [j for j in jobs if j["root"] == root]
        prs, issues = gh.get(root, ([], []))
        busy = any(a["status"] != "idle" for a in mine_a) or mine_j or prs
        if not busy:
            continue
        print(f"\n{short(root)}   {len(issues)} open  {label_counts(issues)}")
        for a in mine_a:
            where = a["ticket"] or Path(a["cwd"]).name
            print(f"  agent {a['status']:<8} {where:<16} {a['title'][:44]}")
        for j in mine_j:
            print("  job   " + job_line(j, 22))
        for p in prs:
            print(f"  pr    #{p['number']:<5} "
                  f"{'draft ' if p['isDraft'] else ''}{p['title'][:58]}")
    quiet = [short(r) for r in roots
             if not any(a["status"] != "idle" for a in agents if a["root"] == r)
             and not [j for j in jobs if j["root"] == r]
             and not gh.get(r, ([], []))[0]]
    if quiet:
        print(f"\nidle, nothing open: {', '.join(quiet)}")


# --- variant c: triage ------------------------------------------------------

def waiting(agents, jobs, gh):
    lines = []
    for a in agents:
        if a["status"] in ("done", "blocked"):
            lines.append(f"agent {a['status']}: {a['ticket'] or a['title']} "
                         f"in {short(a['cwd'])} (pane {a['pane']})")
    for j in jobs:
        if j["state"].startswith(("FAILED", "KILLED")):
            lines.append(f"job {j['name']}: {j['state']} — {j['last'][:50]}")
    for root, (prs, issues) in gh.items():
        name = Path(root).name
        for p in prs:
            if "ready-for-human" in labels(p):
                lines.append(f"PR {name}#{p['number']} is yours to merge: "
                             f"{p['title'][:50]}")
        for i in issues:
            if "ready-for-human" in labels(i):
                lines.append(f"ticket {name}#{i['number']} ready-for-human: "
                             f"{i['title'][:50]}")
    return lines or ["nothing"]


def variant_c(box, agents, jobs, gh):
    room = box["cap"] - box["count"]
    print(f"{box['count']}/{box['cap']} agents, room for {room}, "
          f"load {box['load']:.1f}")
    print("\nNEEDS YOU")
    for line in waiting(agents, jobs, gh):
        print("  " + line)
    print("\nRUNNING")
    for a in agents:
        if a["status"] == "working":
            print(f"  agent  {a['ticket'] or Path(a['cwd']).name:<18} "
                  f"{a['title'][:50]}")
    for j in jobs:
        if j["alive"]:
            print("  job    " + job_line(j, 22))
    idle = sum(1 for a in agents if a["status"] == "idle")
    ended = sum(1 for j in jobs if j["state"] == "ok")
    prs = sum(len(p) for p, _ in gh.values())
    print(f"\n{idle} idle panes, {ended} jobs ended ok in the last hour, "
          f"{prs} open PRs  (stat --all for the rest)")


VARIANTS = {"a": variant_a, "b": variant_b, "c": variant_c}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=sorted(VARIANTS), default="a")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-gh", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    agents, jobs = gather_agents(), gather_jobs()
    box = gather_box(agents)
    roots = sorted({a["root"] for a in agents if os.path.isdir(a["root"])})
    gh = {} if args.no_gh else gather_gh(roots)
    for key in (sorted(VARIANTS) if args.all else [args.variant]):
        print(f"===== variant {key} " + "=" * 60)
        VARIANTS[key](box, agents, jobs, gh)
        print()
    print(f"(gathered in {time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
