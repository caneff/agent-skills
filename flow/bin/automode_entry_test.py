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


def clean_env(**extra):
    """The test's environment with no GIT_* leaking in from a hook or wrapper."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return {**env, **extra}


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=clean_env()
    ).stdout.strip()


class Rig:
    def __init__(self, tmp, via_worktree=False):
        self.tmp = tmp
        self.home = tmp / "home"
        self.repo = tmp / "src"
        self.remote = tmp / "remote.git"
        self.settings = self.repo / "flow" / "claude" / "settings.json"
        self.link = self.home / ".claude" / "settings.json"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True, env=clean_env())
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True, env=clean_env())
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        self.settings.parent.mkdir(parents=True)
        self.write(BASE)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "seed")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        self.link.parent.mkdir(parents=True)
        self.worktree = None
        if via_worktree:  # the live link may point into a linked worktree of the primary checkout
            self.worktree = tmp / "wt"
            git(self.repo, "worktree", "add", "-q", "-b", "wt", str(self.worktree))
            self.settings = self.worktree / "flow" / "claude" / "settings.json"
        self.link.symlink_to(self.settings)

    def write(self, data):
        self.settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def data(self):
        return json.loads(self.settings.read_text())

    def commit_settings(self, text):
        """Replace the settings file's bytes and commit them, so the tree stays clean."""
        self.settings.write_text(text)
        git(self.repo, "commit", "-q", "-am", "edit")

    def stub_claude(self, stdout):
        """A `claude` on PATH that prints stdout for every call."""
        bindir = self.tmp / "bin"
        bindir.mkdir(exist_ok=True)
        stub = bindir / "claude"
        stub.write_text(f"#!/bin/sh\ncat <<'EOF'\n{stdout}\nEOF\n")
        stub.chmod(0o755)
        self.path = f"{bindir}{os.pathsep}{os.environ['PATH']}"

    path = None

    def env(self):
        return clean_env(HOME=str(self.home), **({"PATH": self.path} if self.path else {}))

    def run(self, *args, stdin=None):
        if isinstance(stdin, str):
            stdin = stdin.encode()
        return subprocess.run(
            [str(SCRIPT), *args], env=self.env(), input=stdin or b"", capture_output=True,
            cwd=self.tmp,
        )

    def effective(self):
        out = subprocess.run(
            ["claude", "auto-mode", "config"], env=clean_env(HOME=str(self.home)),
            capture_output=True, text=True, check=True, cwd=self.tmp,
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
        (("add", "allow", "-"), b"bad \xff byte"),  # stdin that is not UTF-8
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
    r = subprocess.run(
        [str(SCRIPT).encode(), b"add", b"allow", b"bad \xff arg"], env=rig.env(), capture_output=True
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


def test_a_settings_entry_that_cannot_be_encoded_is_refused_untouched(rig):
    # A lone-surrogate JSON escape loads fine but cannot be written as UTF-8: the
    # write must fail before the file is opened, not after it is truncated.
    rig.commit_settings(json.dumps({"autoMode": {"allow": ["$defaults", "bad \ud800 entry"]}}))
    before = rig.settings.read_bytes()
    r = rig.run("add", "allow", "fine entry")
    assert r.returncode != 0 and "refused" in out(r)
    assert rig.settings.read_bytes() == before
    assert rig.commits() == 2


def test_open_puts_the_document_in_the_primary_checkout_not_the_worktree(tmp_path):
    rig = Rig(tmp_path, via_worktree=True)
    r = rig.run("open")
    assert r.returncode == 0, out(r)
    assert rig.doc().exists()
    assert not (rig.worktree / ".scratch").exists()


def test_apply_moving_an_entry_between_sections_commits(rig):
    rig.run("open")
    text = rig.doc().read_text().replace("Soft one.\n\n", "").replace(
        "# soft_deny", "Soft one.\n\n# soft_deny"
    )
    rig.doc().write_text(text)  # Soft one. now sits under # allow
    r = rig.run("apply")
    assert r.returncode == 0, out(r)
    d = rig.data()["autoMode"]
    assert "Soft one." in d["allow"] and "Soft one." not in d["soft_deny"]
    assert rig.commits() == 2
    assert git(rig.repo, "rev-parse", "HEAD") == git(rig.remote, "rev-parse", "main")


def test_apply_reorder_within_a_section_commits(rig):
    rig.run("open")
    rig.doc().write_text(
        rig.doc().read_text().replace("Alpha entry.\n\nBeta entry.", "Beta entry.\n\nAlpha entry.")
    )
    r = rig.run("apply")
    assert r.returncode == 0, out(r)
    assert rig.data()["autoMode"]["allow"][1:3] == ["Beta entry.", "Alpha entry."]
    assert rig.commits() == 2


def test_readback_that_disagrees_leaves_the_change_written_but_uncommitted(rig):
    rig.stub_claude('{"allow": [], "soft_deny": [], "environment": []}')
    r = rig.run("add", "allow", "Gamma entry.")
    assert r.returncode != 0 and "MISSING from claude auto-mode config" in out(r)
    assert "not committed" in out(r)
    assert "Gamma entry." in rig.data()["autoMode"]["allow"]
    assert rig.commits() == 1
    again = rig.run("add", "allow", "Delta entry.")  # the dirty file blocks a second edit
    assert again.returncode != 0 and "uncommitted" in out(again)
    assert "Delta entry." not in rig.data()["autoMode"]["allow"]


@pytest.mark.parametrize(
    "printed", ["{}", '{"allow": [], "soft_deny": [], "environment": []}']
)  # the second has the right shape but none of the entries a read file would show
def test_a_removal_is_not_confirmed_by_a_config_that_never_read_the_file(rig, printed):
    rig.run("open")
    rig.doc().write_text(rig.doc().read_text().replace("Beta entry.\n\n", ""))
    rig.stub_claude(printed)
    r = rig.run("apply")
    assert r.returncode != 0 and "not committed" in out(r)
    assert rig.commits() == 1


def test_uncommitted_edits_to_the_settings_file_block_a_write(rig):
    data = rig.data()
    data["permissions"]["allow"].append("Bash(rm -rf /)")
    rig.write(data)
    before = rig.settings.read_bytes()
    r = rig.run("add", "allow", "Gamma entry.")
    assert r.returncode != 0 and "uncommitted" in out(r)
    assert rig.settings.read_bytes() == before
    assert rig.commits() == 1


@pytest.mark.parametrize(
    "edit,why",
    [
        (lambda t: t.replace("# soft_deny\n\n", ""), "missing the heading"),
        (lambda t: t + "\n# allow\n\nLate entry.\n", "appears twice"),
    ],
)
def test_apply_refuses_a_missing_or_repeated_heading(rig, edit, why):
    rig.run("open")
    rig.doc().write_text(edit(rig.doc().read_text()))
    before = rig.settings.read_bytes()
    r = rig.run("apply")
    assert r.returncode != 0 and "refused" in out(r) and why in out(r)
    assert rig.settings.read_bytes() == before
    assert rig.commits() == 1
