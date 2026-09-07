#!/usr/bin/env python3
"""Audit ~/.agents/skills: which model-invocable skills cost context but go unused.

Cross-references each skill's frontmatter (model-invocable?) against the last time
it appears in a Claude Code transcript. Prints a table plus a numbered list of
stale model-invocable skills. Staleness is a signal, not a verdict — "unused" is
not "useless" (read-the-damn-docs fires only when you hit an unfamiliar API), so
the list is yours to pick from. Re-run with `--flip <nums>` to flip the ones you
actually call by hand to `disable-model-invocation: true` (keeps /slash, drops
them from the context window).
"""
import argparse, re, glob, os, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

SKILLS_DIR = os.path.expanduser("~/.agents/skills")
LOGS = os.path.expanduser("~/.claude/projects/**/*.jsonl")  # recurse: subagent logs nest deeper


@dataclass
class Skill:
    name: str
    path: str
    model_invocable: bool
    last_used: Optional[datetime]
    age_days: Optional[int]
    stale: bool

    @classmethod
    def make(cls, name, path, model_invocable, last_used, now, stale_days):
        age_days = (now - last_used).days if last_used else None
        stale = bool(model_invocable and (age_days is None or age_days > stale_days))
        return cls(name, path, model_invocable, last_used, age_days, stale)


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


def add_flag(text):
    """Add `disable-model-invocation: true` to the frontmatter. Idempotent.

    Returns (new_text, changed). Inserts right after the opening `---` fence.
    If the flag is already present in the frontmatter, returns the text
    unchanged.
    """
    lines = text.splitlines(keepends=True)
    # Locate the frontmatter block: the first two `---` fence lines.
    fences = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
    if len(fences) < 2:
        raise ValueError("no frontmatter block")
    top, bot = fences[0], fences[1]
    for ln in lines[top + 1 : bot]:
        if ln.split(":", 1)[0].strip() == "disable-model-invocation":
            return text, False
    lines.insert(top + 1, "disable-model-invocation: true\n")
    return "".join(lines), True


def flip_skill(path):
    with open(path, encoding="utf-8") as f:
        new, changed = add_flag(f.read())
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
    return changed


def _selfcheck():
    fm = parse_frontmatter("---\nname: grill\ndescription: Use when they say: stop.\n---\nbody\n")
    assert fm["name"] == "grill", fm
    assert fm["description"] == "Use when they say: stop.", fm

    src = "---\nname: foo\ndescription: bar\n---\nbody\n"
    out, changed = add_flag(src)
    assert changed and "disable-model-invocation: true" in out, out
    assert out.index("disable-model-invocation") < out.index("name: foo") < out.index("description"), out
    out2, changed2 = add_flag(out)  # idempotent
    assert not changed2 and out2 == out, out2
    assert out.count("disable-model-invocation") == 1, out

    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tf:
        tf.write(src)
        tmp = tf.name
    try:
        assert flip_skill(tmp) is True                 # first flip writes
        assert "disable-model-invocation: true" in open(tmp, encoding="utf-8").read()
        assert flip_skill(tmp) is False                # second is a no-op
    finally:
        os.unlink(tmp)

    now = datetime(2020, 3, 1, tzinfo=timezone.utc)
    used = datetime(2020, 1, 1, tzinfo=timezone.utc)
    fresh = Skill.make("fresh", "/x", True, used, now, 45)
    assert fresh.age_days == 60, fresh
    assert fresh.stale is True, fresh
    quiet = Skill.make("quiet", "/x", False, used, now, 45)
    assert quiet.stale is False, quiet  # not model-invocable, never stale
    never = Skill.make("never", "/x", True, None, now, 45)
    assert never.age_days is None and never.stale is True, never
    recent = Skill.make("recent", "/x", True, now, now, 45)
    assert recent.age_days == 0 and recent.stale is False, recent

    print("ok")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    if argv[:1] == ["--selfcheck"]:
        _selfcheck()
        return 0

    # Args: optional positional stale-days (back-compat), optional `--flip a,b,c`.
    parser = argparse.ArgumentParser()
    parser.add_argument("stale_days", nargs="?", type=int, default=45)
    parser.add_argument("--flip")
    args = parser.parse_args(argv)
    STALE_DAYS = args.stale_days
    flip_nums = [int(x) for x in args.flip.split(",") if x.strip()] if args.flip else None

    paths = {}   # name -> SKILL.md path
    model_inv_by_name = {}  # name -> model_invocable(bool)
    for sk in glob.glob(f"{SKILLS_DIR}/*/SKILL.md"):
        with open(sk, encoding="utf-8", errors="replace") as f:
            fm = parse_frontmatter(f.read())
        name = fm.get("name") or os.path.basename(os.path.dirname(sk))
        disabled = fm.get("disable-model-invocation", "").lower() == "true"
        model_inv_by_name[name] = not disabled
        paths[name] = sk

    last = {}  # name -> datetime
    skill_re = re.compile(r'"skill":"([^"]+)"')
    ts_re = re.compile(r'"timestamp":"([^"]+)"')
    for log in glob.glob(LOGS, recursive=True):
        with open(log, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"skill":"' not in line:
                    continue
                for name in skill_re.findall(line):
                    if name not in model_inv_by_name:
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

    now = datetime.now(timezone.utc)
    rows = [
        Skill.make(name, paths[name], model_inv, last.get(name), now, STALE_DAYS)
        for name, model_inv in model_inv_by_name.items()
    ]

    # sort: model-invocable first, then never-used, then oldest.
    rows.sort(key=lambda r: (r.model_invocable is False, -(r.age_days if r.age_days is not None else 10**6)))

    # Stale candidates, in the stable sorted order the numbered list references.
    targets = [r for r in rows if r.stale]

    # --flip mode: flip the picked numbers against the same list and stop.
    if flip_nums is not None:
        for n in flip_nums:
            if not 1 <= n <= len(targets):
                print(f"  {n}: out of range (1–{len(targets)}) — skipped")
                continue
            skill = targets[n - 1]
            did = flip_skill(skill.path)
            print(f"  {n}. {skill.name}: {'flipped to slash-only' if did else 'already slash-only'}")
        print("\nRe-run without --flip to see the updated report.")
        return 0

    model_ct = sum(1 for r in rows if r.model_invocable)
    print(f"\nSkills in {SKILLS_DIR}: {len(rows)}  |  model-invocable (cost context): {model_ct}")
    print(f"Stale threshold: >{STALE_DAYS} days\n")
    print(f"  {'SKILL':<34} {'INVOKE':<11} {'LAST USED':<11} {'AGE':<9}")
    print("  " + "-" * 62)
    for r in rows:
        inv = "model" if r.model_invocable else "slash-only"
        when = r.last_used.strftime("%Y-%m-%d") if r.last_used else "NEVER"
        ago = f"{r.age_days}d ago" if r.age_days is not None else "—"
        print(f"  {r.name:<34} {inv:<11} {when:<11} {ago:<9}")

    print(f"\n{len(targets)} model-invocable skill(s) unused >{STALE_DAYS}d. "
          "Unused ≠ useless — pick the ones you call by hand, leave the rest:")
    for idx, r in enumerate(targets, 1):
        when = r.last_used.strftime("%Y-%m-%d") if r.last_used else "NEVER"
        print(f"  {idx:>2}. {r.name:<34} last used {when}")
    days_arg = "" if STALE_DAYS == 45 else f"{STALE_DAYS} "
    print(f"\nTo flip: uv run --no-project python {os.path.abspath(__file__)} {days_arg}--flip <nums>   e.g. --flip 1,3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
