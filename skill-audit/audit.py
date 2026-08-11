#!/usr/bin/env python3
"""Audit ~/.agents/skills: which model-invocable skills cost context but go unused.

Cross-references each skill's frontmatter (model-invocable?) against the last time
it appears in a Claude Code transcript. Model-invocable + stale = candidate to flip
to `disable-model-invocation: true` (keeps /slash, drops it from the context window).
"""
import re, glob, os, sys
from datetime import datetime, timezone

SKILLS_DIR = os.path.expanduser("~/.agents/skills")
LOGS = os.path.expanduser("~/.claude/projects/**/*.jsonl")  # recurse: subagent logs nest deeper


def parse_frontmatter(text):
    # Leading ---...--- block, one `key: value` per line. Split on the FIRST
    # colon so a value keeps any later colons (a description often has one).
    fm, seen = {}, 0
    for line in text.splitlines():
        if line.strip() == "---":
            seen += 1
            if seen == 2:
                break
            continue
        if seen == 1 and ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def _selfcheck():
    # A description carrying its own colon must survive the first-colon split.
    fm = parse_frontmatter("---\nname: grill\ndescription: Use when they say: stop.\n---\nbody\n")
    assert fm["name"] == "grill", fm
    assert fm["description"] == "Use when they say: stop.", fm
    print("ok")


if sys.argv[1:2] == ["--selfcheck"]:
    _selfcheck()
    sys.exit()

STALE_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 45

# 1. Parse skills: name + whether model can auto-invoke it.
skills = {}  # name -> model_invocable(bool)
for sk in glob.glob(f"{SKILLS_DIR}/*/SKILL.md"):
    with open(sk, encoding="utf-8", errors="replace") as f:
        fm = parse_frontmatter(f.read())
    name = fm.get("name") or os.path.basename(os.path.dirname(sk))
    disabled = fm.get("disable-model-invocation", "").lower() == "true"
    skills[name] = not disabled

# 2. One pass over transcripts: last-seen timestamp per skill name.
last = {}  # name -> datetime
skill_re = re.compile(r'"skill":"([^"]+)"')
ts_re = re.compile(r'"timestamp":"([^"]+)"')
for log in glob.glob(LOGS, recursive=True):
    with open(log, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"skill":"' not in line:
                continue
            for name in skill_re.findall(line):
                if name not in skills:
                    continue
                m = ts_re.search(line)
                if not m:
                    continue
                try:
                    ts = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if name not in last or ts > last[name]:
                    last[name] = ts

# 3. Report, worst offenders first.
now = datetime.now(timezone.utc)
rows = []
for name, model_inv in skills.items():
    used = last.get(name)
    days = (now - used).days if used else None
    rows.append((name, model_inv, used, days))

# sort: model-invocable first, then never-used, then oldest.
rows.sort(key=lambda r: (r[1] is False, -(r[3] if r[3] is not None else 10**6)))

def fmt(r):
    name, model_inv, used, days = r
    inv = "model" if model_inv else "slash-only"
    when = used.strftime("%Y-%m-%d") if used else "NEVER"
    ago = f"{days}d ago" if days is not None else "—"
    flag = "  <-- FLIP" if model_inv and (days is None or days > STALE_DAYS) else ""
    return f"  {name:<34} {inv:<11} {when:<11} {ago:<9}{flag}"

targets = [r for r in rows if r[1] and (r[3] is None or r[3] > STALE_DAYS)]
model_ct = sum(1 for r in rows if r[1])
print(f"\nSkills in {SKILLS_DIR}: {len(rows)}  |  model-invocable (cost context): {model_ct}")
print(f"Stale threshold: >{STALE_DAYS} days\n")
print(f"  {'SKILL':<34} {'INVOKE':<11} {'LAST USED':<11} {'AGE':<9}")
print("  " + "-" * 62)
for r in rows:
    print(fmt(r))
print(f"\n{len(targets)} model-invocable skill(s) unused >{STALE_DAYS}d — flip to `disable-model-invocation: true` to reclaim context:")
for r in targets:
    print(f"  - {r[0]}")
