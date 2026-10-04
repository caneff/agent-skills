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
import tempfile
import unittest
from pathlib import Path

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


class TeachingHooks(unittest.TestCase):
    # hook -> (precursor command, a sentence from the section it must show)
    CASES = {
        "teach-process-kill.sh": ("ps -eo pid,args", "A kill gets its own Bash call and nothing else."),
        "teach-visual.sh": ("zed docs/x.md:3", "never print a path and ask me to open it"),
        "teach-merge.sh": ("gh pr view 5 --repo caneff/agent-skills", "names its repo"),
        "teach-filing.sh": ('gh issue create --repo caneff/agent-skills --title "teach-lib: x" --body y',
                            "instead of a new issue"),
    }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        stub = self.tmp / "bin"
        stub.mkdir()
        # teach-filing searches open issues; answer "none" without the network.
        (stub / "gh").write_text("#!/usr/bin/env bash\necho '[]'\n")
        (stub / "gh").chmod(0o755)
        self.env = dict(os.environ, XDG_CACHE_HOME=str(self.tmp / "cache"),
                        PATH=f"{stub}:{os.environ['PATH']}")

    def fire(self, command_line, session, cmd):
        payload = json.dumps({"session_id": session, "cwd": str(ROOT), "hook_event_name": "PreToolUse",
                              "tool_name": "Bash", "tool_input": {"command": cmd}})
        p = subprocess.run(command_line, shell=True, input=payload, capture_output=True, text=True,
                           env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        if not p.stdout.strip():
            return ""
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_every_teaching_hook_is_wired_and_teaches_once(self):
        wired = teach_commands()
        self.assertEqual(set(wired), set(self.CASES), "settings.json teaching hooks changed")
        for hook, (cmd, sentence) in self.CASES.items():
            with self.subTest(hook=hook):
                first = self.fire(wired[hook], f"e2e-{hook}", cmd)
                self.assertIn(sentence, first)
                second = self.fire(wired[hook], f"e2e-{hook}", cmd)
                if hook == "teach-filing.sh":
                    # The search answers every filing; the section only once.
                    self.assertNotIn(sentence, second)
                else:
                    self.assertEqual(second, "")


class AlwaysOn(unittest.TestCase):
    def test_budget_gate_passes_on_the_real_tree(self):
        p = subprocess.run([sys.executable, str(ROOT / "tests" / "check-always-on.py")],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("within budget 1100", p.stdout)

    def test_hook_carried_lines_left_claude_md(self):
        text = (CLAUDE / "CLAUDE.md").read_text()
        for gone in ("not-draft", "SHELL-SAFETY", "VISUAL-INSPECTION", "shot-scraper",
                     "search open issues", "# Communication"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)

    def test_communication_lives_in_quill(self):
        quill = (CLAUDE / "output-styles" / "quill.md").read_text()
        self.assertIn("\n# Communication\n", quill)
        self.assertIn("Relay a subagent's or worker's **delta**", quill)


class PathRules(unittest.TestCase):
    WANT = {
        "instruction-files.md": {"**/CLAUDE.md", "**/AGENTS.md", "**/RULES.md", "**/CODING_STANDARDS.md"},
        "skill-files.md": {"**/SKILL.md"},
        "research-notes.md": {"**/docs/research/**"},
    }

    def test_each_rule_is_scoped_to_its_files(self):
        found = {}
        for f in sorted((CLAUDE / "rules").glob("*.md")):
            head = f.read_text().split("---")[1]
            found[f.name] = set(re.findall(r'^\s*-\s*"([^"]+)"', head, re.M))
        self.assertEqual(found, self.WANT)


class Recount(unittest.TestCase):
    def test_count_prints_both_tables(self):
        empty = tempfile.mkdtemp()
        p = subprocess.run([sys.executable, str(CLAUDE / "pointer_reads.py"), "count",
                            "--end", "2026-10-04T00:00:00Z", "--projects", empty],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Sessions in the window: 0.", p.stdout)
        self.assertEqual(p.stdout.count("| SHELL-SAFETY |"), 2)


if __name__ == "__main__":
    unittest.main()
