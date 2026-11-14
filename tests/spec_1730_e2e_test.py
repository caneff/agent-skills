"""End-to-end test for spec #1730: one helper for git, gh and herdr.

The spec's acceptance criteria, driven through the entry points a person or a
nightly job reaches, in throwaway repos whose `origin` is a bare clone given a
github.com URL, with a fake `gh` and a fake `herdr` first on PATH, and a decoy
repo leaked in through `GIT_DIR` on every run:

- the landed page (the spec's one user story): a repo whose `origin/HEAD` is
  unset says so, with the `git remote set-head` that fixes it, and shows no
  commit of another branch or of the leaked repo; a dotted slug links whole;
  no author is printed;
- the nightly backstop on a repo whose `origin/HEAD` is unset is inconclusive
  and names the fix, reads a dotted slug whole, treats a `gh` that cannot say
  who it is as a refusal rather than an answer, and no longer loads drain;
- the helper itself, as its callers use it: a scratch worktree that is gone
  after an exception, a default branch that is read and never guessed, and a
  herdr that hangs being an error inside the timeout, not a worker that left;
- the collapse the spec names: `gitcmd.py` gone, and one home each for the
  git env scrub, the `origin/HEAD` read, the detached scratch worktree, the
  `herdr agent get` probe and the origin-slug regex; every caller the spec and
  its slices name asks git, gh and herdr through the helper, never through a
  bare `subprocess` call, and parses labels through the tracker.

What a green run does NOT cover (the seam, `bash tests/all.sh`, is blind to it):
- GitHub and herdr themselves: the fake `gh` and `herdr` answer the shapes the
  helper and tracker expect, so a real `gh` or `herdr` that changed its output
  is caught only by running the real thing;
- a hung `gh` or `git` in the field: the timeout is witnessed for herdr only;
  `git` and `gh` share its code path in `common/shellcmd.py`;
- callers the spec does not name, the Rust lane's own git and gh code, and the
  shell scripts' git calls (all out of the spec's scope), and a new bare
  `subprocess` git call written in a form the structural check does not parse
  (a command built in a variable before the call);
- whether a model follows the prose in any `SKILL.md` that points at these
  scripts, and the harness behaviours around a run (#925).
"""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LANDED = ROOT / "landed" / "generate.py"
BACKSTOP = ROOT / "backstop" / "backstop.py"
COMMON = ROOT / "common"
SLUG = "me/my.repo"
IDENT = {"GIT_AUTHOR_NAME": "Ada Author", "GIT_AUTHOR_EMAIL": "ada@example.invalid",
         "GIT_COMMITTER_NAME": "Ada Author", "GIT_COMMITTER_EMAIL": "ada@example.invalid"}
REDIRECTS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
             "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")

# The callers spec #1730 and its slices (#1778-#1786) move onto the helper and
# the tracker. Each asks git, gh and herdr through them; none runs a bare one.
NAMED_CALLERS = [
    "all-audits/driver.py", "backstop/backstop.py", "drain/drain.py", "flow/claude/pointer_reads.py",
    "implement-spec/closing_ticket.py", "implement-spec/frontier.py", "implement-spec/loop.py",
    "implement-spec/runfile.py", "implement/codex-audit.py", "implement/codex-audit-range.py",
    "implement/fix_check.py", "implement/pr_settle.py", "implement/selector_check.py",
    "implement/stale_refs.py", "landed/generate.py", "multi-axis-code-review/review_ledger.py",
]
# pointer_reads' slice (#1781) moved its git calls only; its gh read is not in
# any slice's list (#1786 names its gh callers), so only git and herdr are held there.
TOOLS = {"flow/claude/pointer_reads.py": {"git", "herdr"}}

FAKE_GH = """#!/usr/bin/env python3
import os, sys
if os.environ.get("GH_MODE") == "down":
    sys.stderr.write("gh: could not connect to api.github.com\\n"); sys.exit(1)
if sys.argv[1:3] == ["api", "user"]:
    print("me"); sys.exit(0)
sys.stderr.write("fake gh: unexpected call %r\\n" % (sys.argv[1:],)); sys.exit(2)
"""
FAKE_HERDR = """#!/usr/bin/env python3
import json, os, sys, time
mode = os.environ.get("HERDR_MODE", "up")
if mode == "hang":
    time.sleep(60)
if mode == "gone":
    sys.stderr.write(json.dumps({"error": {"code": "agent_not_found", "message": "no agent"}})); sys.exit(1)
if mode == "broken":
    sys.stderr.write("herdr: no server\\n"); sys.exit(1)
print(json.dumps({"result": {"agent": {"name": sys.argv[3], "agent_status": "working", "pane_id": "p1"}}}))
"""
NOTIFIER = """#!/bin/sh
printf '%s\\n%s\\n' "$1" "$2" >> "$NOTIFY_LOG"
"""


def scrubbed():
    return {k: v for k, v in os.environ.items() if k not in REDIRECTS}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={**scrubbed(), **IDENT}).stdout.strip()


def executable(path, text):
    path.write_text(text)
    path.chmod(0o755)
    return path


def commit(repo, name, subject):
    (repo / name).write_text(subject + "\n")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", subject)
    return git(repo, "rev-parse", "HEAD")


def clone_of_bare(tmp, name, url, subject):
    """A checkout cloned from its own bare origin, its origin then given `url`; `origin/HEAD`
    is set, as `git clone` sets it."""
    seed = tmp / f"{name}-seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    commit(seed, "a.txt", subject)
    bare = tmp / f"{name}.git"
    git(tmp, "clone", "-q", "--bare", str(seed), str(bare))
    work = tmp / name
    git(tmp, "clone", "-q", str(bare), str(work))
    git(work, "remote", "set-url", "origin", url)
    return work


@pytest.fixture
def world(tmp_path):
    """Two repos, a decoy leaked in through `GIT_DIR`, fake `gh`/`herdr`, a notifier and a HOME."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    executable(bindir / "gh", FAKE_GH)
    executable(bindir / "herdr", FAKE_HERDR)
    notifier = executable(tmp_path / "notify", NOTIFIER)
    home = tmp_path / "home"
    home.mkdir()
    # The decoy records a default branch, so a reader sent to it by the leaked
    # `GIT_DIR` would list its commits; its origin is not github.com, so a
    # backstop sent to it would say that instead of naming the repo.
    decoy = clone_of_bare(tmp_path, "decoy", "file:///not-github/decoy.git", "DECOY landed")
    # `good` records its default branch and has a dotted slug.
    good = clone_of_bare(tmp_path, "good", f"https://github.com/{SLUG}.git", "GOOD landed")
    # `headless` has the same dotted slug, no `origin/HEAD`, and a local `master`
    # whose commit a guessing reader would show as what landed.
    headless = clone_of_bare(tmp_path, "headless", f"git@github.com:{SLUG}.git", "HEADLESS landed")
    git(headless, "remote", "set-head", "origin", "-d")
    git(headless, "checkout", "-q", "-b", "master")
    commit(headless, "b.txt", "WRONG BRANCH landed")
    env = {**scrubbed(), "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "HOME": str(home),
           "GIT_DIR": str(decoy / ".git"), "NOTIFY_LOG": str(tmp_path / "notify.log"),
           "BACKSTOP_DIR": str(tmp_path / "backstop-state"), "PYTHONDONTWRITEBYTECODE": "1",
           # The origins carry github.com URLs; a run that got past its refusal must not reach the network.
           "GIT_ALLOW_PROTOCOL": "file", "GIT_TERMINAL_PROMPT": "0"}
    return {"tmp": tmp_path, "good": good, "headless": headless, "decoy": decoy, "env": env,
            "notifier": notifier, "notify_log": tmp_path / "notify.log"}


def run(world, cmd, timeout=60, **extra):
    return subprocess.run(cmd, capture_output=True, text=True, env={**world["env"], **extra}, timeout=timeout)


def helper(world, code, **extra):
    """Run `code` with `common/` importable, as a caller does; its stdout, or the failure."""
    try:
        r = run(world, [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(COMMON)!r})\n{code}"],
                timeout=30, **extra)
    except subprocess.TimeoutExpired:
        pytest.fail("the helper call outlived its own timeout: a hung tool was waited on, not refused")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


# --- the landed page: the spec's user story -------------------------------------------------


def test_landed_says_an_unset_origin_head_and_never_shows_another_branch(world):
    out = world["tmp"] / "page" / "landed.html"
    out.parent.mkdir()
    good_sha = git(world["good"], "rev-parse", "origin/main")
    r = run(world, [sys.executable, str(LANDED), "--out", str(out),
                    "--roots", f"{world['good']},{world['headless']}", "50"])
    assert r.returncode == 0, r.stderr + r.stdout
    page = out.read_text()
    headless = page.split('id="pane-headless"', 1)[1]
    assert "cannot list what landed" in headless
    assert "git remote set-head origin -a" in headless
    for wrong in ("WRONG BRANCH landed", "HEADLESS landed", "DECOY landed"):
        assert wrong not in page, f"{wrong!r} shown: a branch other than origin's default was read"
    assert "GOOD landed" in page
    assert f'href="https://github.com/{SLUG}/commit/{good_sha}"' in page, "the dotted slug was cut short"
    assert "Ada Author" not in page and "ada@example.invalid" not in page, "an author column is back"


# --- the nightly backstop -------------------------------------------------------------------


def backstop(world, repo, **extra):
    return run(world, [sys.executable, str(BACKSTOP), "--repo", str(repo), "--jobs", "1",
                       "--notify", str(world["notifier"])], **extra)


def test_backstop_on_an_unset_origin_head_is_inconclusive_and_names_the_fix(world):
    r = backstop(world, world["headless"])
    assert r.returncode == 2, r.stderr + r.stdout  # INCONCLUSIVE: never green, never red
    title, body = world["notify_log"].read_text().splitlines()[:2]
    assert title == f"backstop: {SLUG} inconclusive", "the dotted slug was cut short or the decoy was read"
    assert "origin/HEAD is not set" in body and "git remote set-head origin -a" in body


def test_backstop_reads_a_gh_that_cannot_answer_as_a_refusal(world):
    r = backstop(world, world["good"], GH_MODE="down")
    assert r.returncode == 2, r.stderr + r.stdout
    title, body = world["notify_log"].read_text().splitlines()[:2]
    assert title == f"backstop: {SLUG} inconclusive"
    assert "the `gh` login could not be read" in body and "could not connect" in body


def test_backstop_loads_without_drain(world):
    loaded = helper(world, f"sys.path.insert(0, {str(BACKSTOP.parent)!r})\n"
                           "import backstop\n"
                           "assert backstop._IMPORT_ERROR is None, backstop._IMPORT_ERROR\n"
                           "print(sorted(m for m in sys.modules if m in ('drain', 'gitcmd')))")
    assert loaded == "[]"


# --- the helper, as its callers use it ------------------------------------------------------


def test_the_helper_reads_the_repo_asked_about_and_never_guesses(world):
    good, headless = str(world["good"]), str(world["headless"])
    answers = json.loads(helper(world, f"""
import json, shellcmd
out = {{"default": shellcmd.default_branch({good!r}), "slug": shellcmd.origin_slug({headless!r})}}
try:
    shellcmd.default_branch({headless!r})
except shellcmd.CmdError as e:
    out["refusal"] = str(e)
out["absent"] = shellcmd.git(["-C", {good!r}, "rev-parse", "--verify", "--quiet", "nope"], ok=(0, 1)).returncode
print(json.dumps(out))"""))
    assert answers["default"] == "origin/main"
    assert answers["slug"] == SLUG
    assert "git remote set-head origin -a" in answers.get("refusal", ""), "an unset origin/HEAD was guessed"
    assert answers["absent"] == 1


def test_a_scratch_worktree_is_gone_after_an_exception(world):
    good, scratch = str(world["good"]), str(world["tmp"] / "scratch")
    helper(world, f"""
import shellcmd
try:
    with shellcmd.scratch_worktree({good!r}, "origin/main", {scratch!r}) as p:
        assert open(p + "/a.txt").read() == "GOOD landed\\n"
        raise RuntimeError("the caller failed")
except RuntimeError:
    pass""")
    listed = git(world["good"], "worktree", "list", "--porcelain")
    assert scratch not in listed and not os.path.exists(scratch)


def test_herdr_answers_are_kept_apart_and_a_hung_herdr_is_an_error(world):
    probe = """
import shellcmd
try:
    print(repr(shellcmd.herdr_agent("w1", timeout=2)))
except shellcmd.CmdError as e:
    print("error: " + str(e))"""
    assert "'agent_status': 'working'" in helper(world, probe, HERDR_MODE="up")
    assert helper(world, probe, HERDR_MODE="gone") == "None"
    assert helper(world, probe, HERDR_MODE="broken").startswith("error: ")
    hung = helper(world, probe, HERDR_MODE="hang")
    assert hung.startswith("error: ") and "timed out after 2s" in hung, hung


# --- the collapse: one home for each thing the spec found duplicated --------------------------


def tracked_python():
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.py"], check=True,
                            capture_output=True, text=True, env=scrubbed()).stdout
    return [p for p in listed.split("\0") if p and not p.endswith("_test.py")
            and not p.startswith("tests/") and "fixtures" not in Path(p).name]


@pytest.mark.parametrize("marker, what", [
    ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "the git env scrub"),
    ("refs/remotes/origin/HEAD", "the default-branch read"),
    ('"--detach"', "the detached scratch worktree"),
    ('"agent", "get"', "the `herdr agent get` probe"),
    (r"github\.com[", "the origin-slug regex"),
])
def test_each_duplicated_piece_has_one_home(marker, what):
    homes = [p for p in tracked_python() if marker in (ROOT / p).read_text(errors="replace")]
    assert homes == ["common/shellcmd.py"] or (what == "the origin-slug regex" and set(homes) <= {
        "common/shellcmd.py", "skills-safe-update/scripts/upstream.py"}), f"{what} lives in {homes}"


def test_gitcmd_is_deleted_and_nothing_imports_it():
    assert not (ROOT / "implement" / "gitcmd.py").exists()
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.py"], check=True,
                            capture_output=True, text=True, env=scrubbed()).stdout
    importers = [p for p in listed.split("\0") if p and p != "tests/spec_1730_e2e_test.py"
                 and (ROOT / p).is_file() and "import gitcmd" in (ROOT / p).read_text(errors="replace")]
    assert importers == []


BARE_CALLS = {"run", "Popen", "check_output", "check_call", "call"}


def bare_tool_calls(path, tools):
    """`(line, tool)` of each `subprocess.<call>([<tool>, ...])` in `path` for a tool in `tools`."""
    found = []
    for node in ast.walk(ast.parse((ROOT / path).read_text(), str(path))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in BARE_CALLS and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess" and node.args and isinstance(node.args[0], ast.List)):
            continue
        head = node.args[0].elts[0] if node.args[0].elts else None
        if isinstance(head, ast.Constant) and head.value in tools:
            found.append((node.lineno, head.value))
    return found


@pytest.mark.parametrize("path", NAMED_CALLERS)
def test_a_named_caller_asks_git_gh_and_herdr_through_the_helper(path):
    assert (ROOT / path).is_file(), f"{path} moved; update NAMED_CALLERS"
    bare = bare_tool_calls(path, TOOLS.get(path, {"git", "gh", "herdr"}))
    assert bare == [], f"{path} runs a bare git/gh/herdr (no scrub, no timeout) at {bare}"


@pytest.mark.parametrize("path", NAMED_CALLERS)
def test_a_named_caller_parses_labels_through_the_tracker(path):
    tree = ast.parse((ROOT / path).read_text(), path)
    comps = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)
    parsers = [n.lineno for n in ast.walk(tree) if isinstance(n, comps)
               and "label" in ast.unparse(n).lower() and "['name']" in ast.unparse(n)]
    assert parsers == [], f"{path} parses label names itself at lines {parsers}; tracker.labels is the one parser"
