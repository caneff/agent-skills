#!/usr/bin/env python3
"""End-to-end test for spec #1409, deterministic disclosure levels: every rule
sits at one level, and each level has a loader that does not depend on the
model choosing to read.

What it drives, through the same entry points a session reaches:
- Teaching hooks: each PreToolUse command wired in flow/claude/settings.json,
  fed the precursor command, answers with its doc's section once per session
  and says nothing the second time.
- Always-on text: tests/check-always-on.py passes on the real CLAUDE.md plus
  its imports, and the lines the teaching hooks now carry are gone from it.
- Output style: § Communication is in the repo's Quill copy and not in
  CLAUDE.md.
- Path rules: each file under flow/claude/rules/ scopes itself with `paths:`
  to the files it is about.
- The 14-day re-count: pointer_reads.py count prints both tables.

What a green run does NOT cover (the seam is blind to it):
- whether a model follows any of this text once it is in context;
- a fresh interactive session: that the hooks fire through the live
  ~/.claude/settings.json, that the live ~/.claude/output-styles/quill.md
  matches the repo copy, that the text /memory or an InstructionsLoaded log
  shows is what the budget gate counted, and that `crontab -l` holds the
  tagged re-count line. Those are checked by opening the real thing
  (#1413's closing check), not here;
- the live ~/.claude/rules/ links (`ls -l ~/.claude/rules`, three links into
  flow/claude/rules/), which install.test.sh checks under a scratch HOME
  only: a fourth open of the real thing.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = ROOT / "flow" / "claude"
LIVE_PREFIX = "/home/caneff/.agents/skills/"  # how settings.json names this repo


def teach_commands():
    settings = json.loads((CLAUDE / "settings.json").read_text())
    out = {}
    for entry in settings["hooks"]["PreToolUse"]:
        for h in entry["hooks"]:
            m = re.search(r"flow/claude/hooks/(teach-[a-z-]+\.sh)", h["command"])
            if m:
                out[m.group(1)] = h["command"].replace(LIVE_PREFIX, f"{ROOT}/")
    return out


# hook -> (precursor command, a sentence from the section it must show)
TEACH_CASES = {
    "teach-process-kill.sh": ("ps -eo pid,args", "A kill gets its own Bash call and nothing else."),
    "teach-visual.sh": ("zed docs/x.md:3", "never print a path and ask me to open it"),
    "teach-merge.sh": ("gh pr view 5 --repo caneff/agent-skills", "names its repo"),
    "teach-filing.sh": ('gh issue create --repo caneff/agent-skills --title "teach-lib: x" --body y',
                        "instead of a new issue"),
}


@pytest.fixture
def hook_env(tmp_path):
    stub = tmp_path / "bin"
    stub.mkdir()
    # teach-filing searches open issues; answer "none" without the network.
    (stub / "gh").write_text("#!/usr/bin/env bash\necho '[]'\n")
    (stub / "gh").chmod(0o755)
    return dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "cache"), PATH=f"{stub}:{os.environ['PATH']}")


def fire(env, command_line, session, cmd):
    payload = json.dumps({"session_id": session, "cwd": str(ROOT), "hook_event_name": "PreToolUse",
                          "tool_name": "Bash", "tool_input": {"command": cmd}})
    p = subprocess.run(command_line, shell=True, input=payload, capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    if not p.stdout.strip():
        return ""
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def test_every_teaching_hook_is_wired():
    assert set(teach_commands()) == set(TEACH_CASES), "settings.json teaching hooks changed"


@pytest.mark.parametrize("hook", sorted(TEACH_CASES))
def test_a_teaching_hook_teaches_once(hook, hook_env):
    cmd, sentence = TEACH_CASES[hook]
    command_line = teach_commands()[hook]
    first = fire(hook_env, command_line, f"e2e-{hook}", cmd)
    assert sentence in first
    second = fire(hook_env, command_line, f"e2e-{hook}", cmd)
    if hook == "teach-filing.sh":
        # The search answers every filing; the section only once.
        assert sentence not in second
    else:
        assert second == ""


def test_budget_gate_passes_on_the_real_tree():
    p = subprocess.run([sys.executable, str(ROOT / "tests" / "check-always-on.py")],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "within budget 1100" in p.stdout


@pytest.mark.parametrize("gone", ["not-draft", "SHELL-SAFETY", "zed <path>", "shot-scraper",
                                  "search open issues", "# Communication"])
def test_hook_carried_lines_left_claude_md(gone):
    assert gone not in (CLAUDE / "CLAUDE.md").read_text()


def test_communication_lives_in_quill():
    quill = (CLAUDE / "output-styles" / "quill.md").read_text()
    assert "\n# Communication\n" in quill
    assert "Relay a subagent's or worker's **delta**" in quill


WANT_RULE_PATHS = {
    "instruction-files.md": {"**/CLAUDE.md", "**/AGENTS.md", "**/RULES.md", "**/CODING_STANDARDS.md"},
    "skill-files.md": {"**/SKILL.md"},
    "research-notes.md": {"**/docs/research/**"},
}


def test_each_rule_is_scoped_to_its_files():
    found = {}
    for f in sorted((CLAUDE / "rules").glob("*.md")):
        head = f.read_text().split("---")[1]
        found[f.name] = set(re.findall(r'^\s*-\s*"([^"]+)"', head, re.M))
    assert found == WANT_RULE_PATHS


def test_recount_count_prints_both_tables(tmp_path):
    p = subprocess.run([sys.executable, str(CLAUDE / "pointer_reads.py"), "count",
                        "--end", "2026-10-04T00:00:00Z", "--projects", str(tmp_path)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "Sessions in the window: 0." in p.stdout
    assert p.stdout.count("| SHELL-SAFETY |") == 2
