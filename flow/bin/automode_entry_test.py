"""Contract tests for flow/bin/automode-entry (#1534).

Every test runs the command as Chris would, against a fake HOME whose
~/.claude/settings.json is a symlink into a throwaway git repo (with a bare
remote), and reads the real `claude auto-mode config` back. Nothing here
touches the live settings.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("automode-entry")
ODD = "Odd   spacing\tentry."  # collapses to one space per run of whitespace
BASE = {
    "env": {"X": "1"},
    "permissions": {"allow": ["Bash(ls)"]},
    "autoMode": {
        "allow": ["$defaults", "Alpha entry.", "Beta entry.", ODD],
        "soft_deny": ["$defaults", "Soft one."],
        "environment": ["$defaults"],
    },
}


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


class Rig:
    def __init__(self, tmp):
        self.home = tmp / "home"
        self.repo = tmp / "src"
        self.remote = tmp / "remote.git"
        self.settings = self.repo / "flow" / "claude" / "settings.json"
        self.link = self.home / ".claude" / "settings.json"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        self.settings.parent.mkdir(parents=True)
        self.write(BASE)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "seed")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(self.settings)

    def write(self, data):
        self.settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def data(self):
        return json.loads(self.settings.read_text())

    def run(self, *args, stdin=None):
        env = {**os.environ, "HOME": str(self.home)}
        for k in [k for k in env if k.startswith("GIT_")]:
            del env[k]
        if isinstance(stdin, str):
            stdin = stdin.encode()
        return subprocess.run(
            [str(SCRIPT), *args], env=env, input=stdin or b"", capture_output=True,
        )

    def effective(self):
        env = {**os.environ, "HOME": str(self.home)}
        out = subprocess.run(
            ["claude", "auto-mode", "config"], env=env, capture_output=True, text=True, check=True
        ).stdout
        return {e for v in json.loads(out).values() for e in v}

    def commits(self):
        return int(git(self.repo, "rev-list", "--count", "HEAD"))

    def doc(self):
        return self.repo / ".scratch" / "automode.md"


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def out(r):
    return r.stdout.decode() + r.stderr.decode()


def test_add_appends_shows_rule_and_commits_and_pushes(rig):
    r = rig.run("add", "allow", "Gamma entry.")
    assert r.returncode == 0, out(r)
    assert rig.data()["autoMode"]["allow"][-1] == "Gamma entry."
    assert rig.link.is_symlink() and rig.link.resolve() == rig.settings.resolve()
    assert "Gamma entry." in rig.effective()
    assert "in claude auto-mode config" in out(r)
    assert rig.commits() == 2
    assert git(rig.repo, "show", "--name-only", "--format=", "HEAD") == "flow/claude/settings.json"
    assert git(rig.repo, "rev-parse", "HEAD") == git(rig.remote, "rev-parse", "main")
    assert rig.data()["permissions"] == BASE["permissions"]


def test_add_reads_text_from_stdin_and_file(rig, tmp_path):
    assert rig.run("add", "soft_deny", "-", stdin="Line one\nline two.\n").returncode == 0
    f = tmp_path / "entry.txt"
    f.write_text("From a file.\n")
    assert rig.run("add", "environment", f"@{f}").returncode == 0
    d = rig.data()["autoMode"]
    assert d["soft_deny"][-1] == "Line one line two."
    assert d["environment"][-1] == "From a file."


@pytest.mark.parametrize(
    "args,stdin",
    [
        (("add", "nonsense", "x"), None),
        (("add", "allow", "   "), None),
        (("add", "allow", "Alpha entry."), None),  # duplicate
        (("add", "allow", "-"), b"bad \xff byte"),  # would not serialize as UTF-8
    ],
)
def test_add_refusals_leave_file_and_history_alone(rig, args, stdin):
    before = rig.settings.read_bytes()
    r = rig.run(*args, stdin=stdin)
    assert r.returncode != 0 and "refused" in out(r)
    assert rig.settings.read_bytes() == before
    assert rig.link.is_symlink()
    assert rig.commits() == 1


def test_add_refuses_an_argument_that_is_not_utf8(rig):
    before = rig.settings.read_bytes()
    env = {**os.environ, "HOME": str(rig.home)}
    r = subprocess.run(
        [str(SCRIPT).encode(), b"add", b"allow", b"bad \xff arg"], env=env, capture_output=True
    )
    assert r.returncode != 0 and "refused" in out(r)
    assert rig.settings.read_bytes() == before


def test_unparseable_settings_are_refused_untouched(rig):
    rig.settings.write_text("{ not json")
    r = rig.run("add", "allow", "x")
    assert r.returncode != 0 and "refused" in out(r)
    assert rig.settings.read_text() == "{ not json"


def test_open_writes_one_paragraph_per_entry_under_section_headings(rig):
    r = rig.run("open")
    assert r.returncode == 0, out(r)
    assert str(rig.doc()) in out(r)
    assert ".claude/worktrees" not in str(rig.doc())
    paras = [p for p in rig.doc().read_text().split("\n\n") if p.strip()]
    heads = [p for p in paras if p.startswith("# ")]
    assert heads == ["# allow", "# soft_deny", "# environment"]
    assert "Alpha entry." in paras and "Soft one." in paras


def test_apply_diffs_per_entry_writes_in_place_and_commits(rig):
    rig.run("open")
    text = rig.doc().read_text()
    text = text.replace("Alpha entry.", "Gamma entry.").replace("Beta entry.\n\n", "")
    text = text.replace("# environment", "Soft two.\n\n# environment")  # lands in soft_deny
    rig.doc().write_text(text)
    r = rig.run("apply")
    assert r.returncode == 0, out(r)
    d = rig.data()["autoMode"]
    assert d["allow"] == ["$defaults", "Gamma entry.", ODD]
    assert d["soft_deny"] == ["$defaults", "Soft one.", "Soft two."]
    assert rig.link.is_symlink() and rig.link.resolve() == rig.settings.resolve()
    shown = out(r)
    assert "+ allow: Gamma entry." in shown and "- allow: Alpha entry." in shown
    assert "- allow: Beta entry." in shown and "+ soft_deny: Soft two." in shown
    eff = rig.effective()
    assert "Gamma entry." in eff and "Beta entry." not in eff and "Soft two." in eff
    assert rig.commits() == 2
    assert git(rig.repo, "rev-parse", "HEAD") == git(rig.remote, "rev-parse", "main")


def test_apply_of_an_untouched_document_changes_nothing(rig):
    rig.run("open")
    before = rig.settings.read_bytes()
    r = rig.run("apply")
    assert r.returncode == 0 and "no changes" in out(r)
    assert rig.settings.read_bytes() == before  # ODD keeps its original whitespace
    assert rig.commits() == 1


@pytest.mark.parametrize(
    "edit,why",
    [
        (lambda t: t.replace("# soft_deny", "# nonsense"), "unknown section"),
        (lambda t: "stray text\n\n" + t, "before the first"),
    ],
)
def test_apply_refuses_a_malformed_document(rig, edit, why):
    rig.run("open")
    rig.doc().write_text(edit(rig.doc().read_text()))
    before = rig.settings.read_bytes()
    r = rig.run("apply")
    assert r.returncode != 0 and "refused" in out(r) and why in out(r)
    assert rig.settings.read_bytes() == before
    assert rig.commits() == 1


def test_apply_refuses_when_settings_moved_since_open(rig):
    rig.run("open")
    assert rig.run("add", "allow", "Added meanwhile.").returncode == 0
    rig.doc().write_text(rig.doc().read_text().replace("Alpha entry.", "Gamma entry."))
    before = rig.settings.read_bytes()
    r = rig.run("apply")
    assert r.returncode != 0 and "changed since open" in out(r)
    assert rig.settings.read_bytes() == before


def test_apply_without_open_is_refused(rig):
    r = rig.run("apply")
    assert r.returncode != 0 and "run `automode-entry open` first" in out(r)
