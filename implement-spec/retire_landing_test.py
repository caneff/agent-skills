"""Tests for `implement-spec/retire_landing.py`, spec #1634's landing script.

One seam: its command line and exit codes, against a fake `job-run`, `herdr`,
`gh` and `cargo`, and real git checkouts under a temp HOME. This file holds no
literal of the retired word: `retire_landing.py` is the one exempt path, so
every fixture takes the word from that module's constants.
"""
import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retire_landing as landing  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "retire_landing.py")
OWN = "spec-1634-20261103"

FAKE_JOB_RUN = """#!/bin/bash
# job-run's --status contract: first word and exit code, off a state file.
d="$HOME/.cache/agent-jobs/$2"
[ -d "$d" ] || { echo "unknown $2: no run directory"; exit 12; }
case "$(cat "$d/state")" in
  alive) echo "alive $2 pid=1"; exit 10 ;;
  killed) echo "killed $2 pid=1"; exit 11 ;;
  *) echo "finished $2 rc=0"; exit 0 ;;
esac
"""
FAKE_HERDR = """#!/bin/bash
cat "$HOME/fake-herdr.json"
"""
FAKE_CARGO = """#!/bin/bash
# `cargo install --root "$HOME/.local"`, as flow/lane-install.sh runs it: one
# logged call, and a binary whose --help says what the fixture says it does.
echo "$@" >> "$HOME/cargo-calls"
[ -e "$HOME/cargo-fails" ] && { echo "error: boom" >&2; exit 1; }
printf '#!/bin/bash\\necho "under %s"\\n' "$(cat "$HOME/cargo-builds")" \\
  > "$HOME/.local/bin/implement-dispatch"
chmod +x "$HOME/.local/bin/implement-dispatch"
"""
FAKE_GH = f"""#!{sys.executable}
import json, os, sys
home = os.environ["HOME"]
store = os.path.join(home, "gh-issues.json")
issues = json.load(open(store))
args = sys.argv[1:]
if os.path.exists(os.path.join(home, "gh-fails")):
    sys.exit("gh: boom")
if args[:2] == ["issue", "list"]:
    canned = os.path.join(home, "gh-list-answer")
    print(open(canned).read() if os.path.exists(canned) else json.dumps(
        [{{"number": i["number"], "title": i["title"]}} for i in issues]))
elif args[:2] == ["issue", "create"]:
    number = 2000 + len(issues)
    issues.append({{"number": number, "args": args, "body": sys.stdin.read(),
                    "title": args[args.index("--title") + 1]}})
    json.dump(issues, open(store, "w"))
    print(os.environ.get("FAKE_GH_URL", f"https://example.test/issues/{{number}}"))
"""


def write_tool(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class World:
    """A temp HOME and PATH: one finished drain job, a live `herdr` with an
    unrelated pane, and this retirement's own run file."""

    def __init__(self, tmp_path):
        self.home = tmp_path / "home"
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.old_cache = self.home / landing.OLD_CACHE
        self.new_cache = self.home / landing.NEW_CACHE
        self.old_cache.mkdir(parents=True)
        (self.home / landing.JOBS_DIR).mkdir(parents=True)
        for tool in ("git", "rg"):
            os.symlink(shutil.which(tool), self.bin / tool)
        write_tool(self.bin / "job-run", FAKE_JOB_RUN)
        write_tool(self.bin / "herdr", FAKE_HERDR)
        write_tool(self.bin / "cargo", FAKE_CARGO)
        write_tool(self.bin / "gh", FAKE_GH)
        self.origins = tmp_path / "origins"
        self.job("drain-skills", "finished")
        self.run_file(OWN, ["skills-1635"], controller="skills-spec-1634")
        self.panes("skills-1635", "skills-spec-1634", None)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("GIT_", "RIPGREP_"))}
        self.env.update(HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1",
                        PATH=f"{self.bin}:/usr/bin:/bin")

    def job(self, name, state):
        job = self.home / landing.JOBS_DIR / name
        job.mkdir()
        (job / "state").write_text(state)

    def run_file(self, run_id, agents, controller="ctl", cache=None):
        body = {"run_id": run_id, "controller": controller,
                "clumps": [{"agent": a, "tickets": [1]} for a in agents]}
        (cache or self.old_cache).joinpath(f"{run_id}.json").write_text(
            json.dumps(body))

    def panes(self, *names):
        """`herdr agent list` as the real one answers: `name` on a named pane,
        no such key on any other."""
        agents = [{"agent": "claude", **({"name": n} if n else {})}
                  for n in names]
        self.herdr_answers(json.dumps({"result": {"agents": agents}}))

    def herdr_answers(self, text):
        (self.home / "fake-herdr.json").write_text(text)

    def script(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, *args], env=self.env, text=True,
            capture_output=True, check=False)

    def check(self):
        return self.script("check", "--own-run", OWN)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def refused(result, cause):
    """Exit 1, for the named cause: a refusal for some other reason is not the
    behaviour a case claims."""
    assert result.returncode == 1, result.stdout + result.stderr
    assert cause in result.stdout, result.stdout + result.stderr


def test_check_passes_when_only_its_own_run_is_alive(world):
    world.run_file("spec-57-20261103", ["sudoku-kit-58"])
    result = world.check()
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_refuses_a_live_drain(world):
    world.job("drain-sudoku-kit", "alive")
    refused(world.check(), "drain-sudoku-kit")


@pytest.mark.parametrize("state", ["finished", "killed"])
def test_check_passes_a_drain_that_ended(world, state):
    world.job("drain-sudoku-kit", state)
    assert world.check().returncode == 0


def test_check_refuses_a_live_worker_of_another_run(world):
    world.run_file("spec-57-20261103", ["sudoku-kit-58"])
    world.panes("skills-1635", "sudoku-kit-58")
    result = world.check()
    refused(result, "sudoku-kit-58")
    assert "spec-57-20261103" in result.stdout


def test_check_refuses_a_live_controller_of_another_run(world):
    world.run_file("spec-57-20261103", ["sudoku-kit-58"],
                   controller="sudoku-kit-spec-57")
    world.panes("skills-1635", "sudoku-kit-spec-57")
    refused(world.check(), "sudoku-kit-spec-57")


def test_check_reads_run_files_already_moved_to_the_new_cache(world):
    world.new_cache.mkdir()
    world.run_file("spec-57-20261103", ["sudoku-kit-58"], cache=world.new_cache)
    world.panes("skills-1635", "sudoku-kit-58")
    refused(world.check(), "sudoku-kit-58")


def test_check_refuses_an_own_run_with_no_run_file(world):
    result = world.script("check", "--own-run", "spec-1-typo")
    refused(result, "spec-1-typo")


def test_check_ignores_cache_json_that_is_not_a_run_file(world):
    (world.old_cache / "spec-66.candidates.json").write_text("[]")
    (world.old_cache / "ws-130.json").write_text('{"id": "x", "ok": true}')
    assert world.check().returncode == 0


@pytest.mark.parametrize("body", ["{not json", '{"run_id": "x", "clumps": 3}',
                                  '{"run_id": "x", "clumps": [{"tickets": [1]}]}'])
def test_check_refuses_a_run_file_it_cannot_read(world, body):
    (world.old_cache / "spec-9.json").write_text(body)
    refused(world.check(), "spec-9.json")


@pytest.mark.parametrize("tool_body", [
    None,
    "#!/bin/bash\necho 'job-run: boom' >&2\nexit 1\n",
    "#!/bin/bash\nexit 0\n",
    "#!/bin/bash\nexit 12\n",
], ids=["missing", "fails", "silent-success", "silent-unknown"])
def test_check_refuses_when_job_run_cannot_be_read(world, tool_body):
    (world.bin / "job-run").unlink()
    if tool_body:
        write_tool(world.bin / "job-run", tool_body)
    refused(world.check(), "job-run")


def test_check_refuses_when_the_jobs_directory_is_absent(world):
    shutil.rmtree(world.home / landing.JOBS_DIR)
    refused(world.check(), str(landing.JOBS_DIR))


@pytest.mark.parametrize("answer", [
    "not json", "{}", '{"result": {"agents": 3}}', '{"result": {"agents": []}}',
    '{"result": {"agents": ["x"]}}',
], ids=["not-json", "no-result", "not-a-list", "empty", "not-an-object"])
def test_check_refuses_an_unusable_herdr_answer(world, answer):
    world.herdr_answers(answer)
    refused(world.check(), "herdr")


def test_check_refuses_when_herdr_fails(world):
    write_tool(world.bin / "herdr", "#!/bin/bash\necho 'no server' >&2\nexit 1\n")
    refused(world.check(), "no server")


def test_check_refuses_when_herdr_is_missing(world):
    (world.bin / "herdr").unlink()
    refused(world.check(), "herdr")


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], text=True,
                          capture_output=True, check=True).stdout.strip()


class Landing(World):
    """A World ready for `finish`: a cache to move, an old binary, the skill
    link, three checkouts with their citations pushed, and no ticket yet."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        (self.old_cache / "burn-old.json").write_text('{"run_id": "burn-old", "clumps": []}')
        (self.old_cache / "burn-old.d").mkdir()
        (self.old_cache / "burn-old.d" / "note").write_text("kept")
        self.cache_before = self.tree(self.old_cache)
        self.binary = self.home / ".local/bin/implement-dispatch"
        self.binary.parent.mkdir(parents=True)
        write_tool(self.binary, f'#!/bin/bash\necho "under {landing.OLD_CACHE}"\n')
        (self.home / "cargo-builds").write_text(landing.NEW_CACHE)
        self.link = self.home / landing.SKILL_LINK
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(self.home)
        (self.home / "gh-issues.json").write_text("[]")
        self.origins.mkdir()
        for repo, edits in landing.REPOS.items():
            self.checkout(repo, "# Repo\n\n" + "\n\n".join(old for old, _ in edits) + "\n")

    def checkout(self, repo, agents_md):
        origin = self.origins / f"{repo}.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        clone = self.clone(repo)
        clone.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)],
                       check=True, capture_output=True)
        git(clone, "checkout", "-q", "-b", "main")
        git(clone, "config", "user.email", "t@example.test")
        git(clone, "config", "user.name", "t")
        (clone / "AGENTS.md").write_text(agents_md)
        git(clone, "add", "AGENTS.md")
        git(clone, "commit", "-q", "-m", "seed")
        git(clone, "push", "-q", "origin", "main")

    def clone(self, repo):
        return self.home / "src" / repo

    def finish(self):
        return self.script("finish", "--own-run", OWN)

    @staticmethod
    def tree(root):
        return {str(p.relative_to(root)): p.read_text()
                for p in root.rglob("*") if p.is_file()}

    def origin_commits(self, repo):
        """Commits on origin's main past the seed."""
        return git(self.origins / f"{repo}.git", "log", "--format=%s", "main").splitlines()[:-1]

    def issues(self):
        return json.loads((self.home / "gh-issues.json").read_text())

    def cargo_calls(self):
        calls = self.home / "cargo-calls"
        return len(calls.read_text().splitlines()) if calls.exists() else 0

    def assert_complete(self):
        """Everything `finish` owes, each counted once."""
        moved = self.tree(self.new_cache)
        assert not self.old_cache.exists()
        for name, body in self.cache_before.items():
            assert moved[name] == body
        assert landing.NEW_CACHE in subprocess.run(
            [str(self.binary), "--help"], text=True, capture_output=True, check=True).stdout
        assert not self.link.is_symlink() and not self.link.exists()
        for repo in landing.REPOS:
            assert self.origin_commits(repo) == [landing.COMMIT_SUBJECT], repo
            on_origin = git(self.origins / f"{repo}.git", "show", "main:AGENTS.md")
            assert landing.RETIRED not in on_origin.lower(), repo
            assert git(self.clone(repo), "status", "--porcelain") == "", repo
        assert len(self.issues()) == 1


@pytest.fixture
def land(tmp_path):
    return Landing(tmp_path)


def test_finish_does_every_step_once(land):
    result = land.finish()
    assert result.returncode == 0, result.stdout + result.stderr
    land.assert_complete()
    assert land.cargo_calls() == 1


def test_finish_files_a_removal_ticket_a_queue_can_pick_up(land):
    assert land.finish().returncode == 0
    ticket = land.issues()[0]
    assert ticket["title"] == landing.REMOVAL_TITLE
    assert ticket["args"][ticket["args"].index("--label") + 1] == "ready-for-agent"
    assert ticket["args"][ticket["args"].index("--repo") + 1] == "caneff/agent-skills"
    assert "## Blocked by\n\n- #1634" in ticket["body"]
    assert "implement-spec/retire_landing.py" in ticket["body"]


def test_a_second_finish_changes_nothing(land):
    assert land.finish().returncode == 0
    result = land.finish()
    assert result.returncode == 0, result.stdout + result.stderr
    land.assert_complete()
    assert land.cargo_calls() == 1


def test_finish_touches_nothing_while_a_drain_is_alive(land):
    land.job("drain-sudoku-kit", "alive")
    refused(land.finish(), "drain-sudoku-kit")
    assert land.tree(land.old_cache) == land.cache_before
    assert land.link.is_symlink()
    assert land.cargo_calls() == 0
    assert land.issues() == []


def _cache_conflict(land):
    land.new_cache.mkdir()
    (land.new_cache / "burn-old.json").write_text("other")
    return lambda: (land.new_cache / "burn-old.json").unlink()


def _cargo_fails(land):
    marker = land.home / "cargo-fails"
    marker.touch()
    return marker.unlink


def _link_is_a_directory(land):
    land.link.unlink()
    land.link.mkdir()
    return land.link.rmdir


def _commit_refused(land):
    hook = land.clone("sudokupad-art") / ".git/hooks/pre-commit"
    write_tool(hook, "#!/bin/bash\nexit 1\n")
    return hook.unlink


def _push_refused(land):
    hook = land.origins / "sudokupad-art.git/hooks/pre-receive"
    write_tool(hook, "#!/bin/bash\nexit 1\n")
    return hook.unlink


def _gh_fails(land):
    marker = land.home / "gh-fails"
    marker.touch()
    return marker.unlink


@pytest.mark.parametrize("fault, cause", [
    (_cache_conflict, "burn-old.json"),
    (_cargo_fails, "lane-install.sh"),
    (_link_is_a_directory, "not a symlink"),
    (_commit_refused, "sudokupad-art"),
    (_push_refused, "sudokupad-art"),
    (_gh_fails, "gh issue list"),
], ids=["cache", "rebuild", "link", "commit", "push", "ticket"])
def test_finish_rerun_after_a_stop_completes_without_repeating(land, fault, cause):
    clear = fault(land)
    stopped = land.finish()
    refused(stopped, cause)
    clear()
    result = land.finish()
    assert result.returncode == 0, result.stdout + result.stderr
    land.assert_complete()
    assert land.cargo_calls() >= 1


def test_a_stop_before_the_repos_runs_no_later_step(land):
    _cargo_fails(land)
    refused(land.finish(), "lane-install.sh")
    assert land.link.is_symlink()
    assert land.issues() == []
    assert land.origin_commits("sudokupad-art") == []


def test_a_successful_rebuild_is_not_run_again_after_a_later_stop(land):
    clear = _link_is_a_directory(land)
    assert land.finish().returncode == 1
    clear()
    assert land.finish().returncode == 0
    assert land.cargo_calls() == 1


def test_a_commit_that_reached_only_the_checkout_is_pushed_not_remade(land):
    clear = _push_refused(land)
    assert land.finish().returncode == 1
    assert git(land.clone("sudokupad-art"), "log", "-1", "--format=%s") == landing.COMMIT_SUBJECT
    assert land.origin_commits("sudokupad-art") == []
    clear()
    assert land.finish().returncode == 0
    assert land.origin_commits("sudokupad-art") == [landing.COMMIT_SUBJECT]


def test_a_dirty_checkout_stops_only_its_own_step(land):
    stray = land.clone("sudokupad-art") / "stray.txt"
    stray.write_text("work in progress")
    result = land.finish()
    refused(result, "sudokupad-art")
    assert "stray.txt" in result.stdout
    assert land.origin_commits("sudokupad-art") == []
    assert stray.read_text() == "work in progress"
    assert land.origin_commits("twitch-rules-scroller") == [landing.COMMIT_SUBJECT]
    assert land.origin_commits("sudokumaker-custom-constraints") == [landing.COMMIT_SUBJECT]
    stray.unlink()
    assert land.finish().returncode == 0
    land.assert_complete()


def test_a_dirty_checkout_whose_fix_already_landed_does_not_stop(land):
    assert land.finish().returncode == 0
    (land.clone("sudokupad-art") / "stray.txt").write_text("later work")
    assert land.finish().returncode == 0


def test_a_checkout_off_main_stops_its_step(land):
    git(land.clone("sudokupad-art"), "checkout", "-q", "-b", "other")
    refused(land.finish(), "on branch other")
    assert land.origin_commits("sudokupad-art") == []


def test_an_unpushed_commit_of_someone_elses_is_not_pushed(land):
    clone = land.clone("sudokupad-art")
    (clone / "other.txt").write_text("x")
    git(clone, "add", "other.txt")
    git(clone, "commit", "-q", "-m", "someone's work")
    refused(land.finish(), "someone's work")
    assert land.origin_commits("sudokupad-art") == []


def test_a_checkout_behind_origin_is_brought_up_first(land):
    origin = land.origins / "sudokupad-art.git"
    other = land.home / "other-clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True, capture_output=True)
    git(other, "config", "user.email", "t@example.test")
    git(other, "config", "user.name", "t")
    (other / "new.txt").write_text("x")
    git(other, "add", "new.txt")
    git(other, "commit", "-q", "-m", "newer")
    git(other, "push", "-q", "origin", "main")
    result = land.finish()
    assert result.returncode == 0, result.stdout + result.stderr
    assert land.origin_commits("sudokupad-art") == [landing.COMMIT_SUBJECT, "newer"]


def test_a_missing_checkout_stops_its_step_and_fails_the_last_step(land):
    shutil.rmtree(land.clone("sudokupad-art"))
    refused(land.finish(), "sudokupad-art")


def test_the_last_step_fails_until_the_word_is_gone_from_all_three(land):
    clone = land.clone("twitch-rules-scroller")
    text = (clone / "AGENTS.md").read_text()
    (clone / "AGENTS.md").write_text(text + f"\nSee {landing.RETIRED}, unforeseen.\n")
    git(clone, "commit", "-q", "-am", "unforeseen citation")
    git(clone, "push", "-q", "origin", "main")
    result = land.finish()
    refused(result, "unforeseen")
    assert len(land.issues()) == 1
    text = (clone / "AGENTS.md").read_text()
    (clone / "AGENTS.md").write_text(text.replace(f"See {landing.RETIRED}, unforeseen.\n", ""))
    git(clone, "commit", "-q", "-am", "worded by a person")
    git(clone, "push", "-q", "origin", "main")
    result = land.finish()
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(land.issues()) == 1


def test_the_last_step_fails_when_rg_cannot_answer(land):
    (land.bin / "rg").unlink()
    write_tool(land.bin / "rg", "#!/bin/bash\necho 'rg: boom' >&2\nexit 2\n")
    refused(land.finish(), "rg: boom")


def test_the_carried_wording_leaves_none_of_the_word_behind(land):
    for edits in landing.REPOS.values():
        for _, new in edits:
            assert landing.RETIRED not in new.lower()
            assert "clumper" not in new.lower()


def test_cache_files_that_reappear_at_the_old_path_are_moved_too(land):
    assert land.finish().returncode == 0
    land.old_cache.mkdir()
    (land.old_cache / "late.json.lock").write_text("late")
    assert land.finish().returncode == 0
    assert not land.old_cache.exists()
    assert (land.new_cache / "late.json.lock").read_text() == "late"
    assert (land.new_cache / "burn-old.d" / "note").read_text() == "kept"


def test_a_cache_conflict_overwrites_and_deletes_nothing(land):
    land.new_cache.mkdir()
    (land.new_cache / "burn-old.json").write_text("other")
    refused(land.finish(), "burn-old.json")
    assert (land.new_cache / "burn-old.json").read_text() == "other"
    assert (land.old_cache / "burn-old.json").read_text() == land.cache_before["burn-old.json"]


def test_an_install_that_leaves_the_old_binary_fails(land):
    (land.home / "cargo-builds").write_text(landing.OLD_CACHE)
    refused(land.finish(), landing.NEW_CACHE)


def test_the_ticket_is_not_filed_again_when_it_is_already_closed(land):
    (land.home / "gh-issues.json").write_text(json.dumps(
        [{"number": 7, "title": landing.REMOVAL_TITLE}]))
    assert land.finish().returncode == 0
    assert len(land.issues()) == 1


@pytest.mark.parametrize("listing, cause", [
    ("not json", "gh issue list"),
    ('{"no": "list"}', "gh issue list"),
    (json.dumps([{"number": i, "title": "x"} for i in range(landing.ISSUE_LIMIT)]), "limit"),
], ids=["not-json", "not-a-list", "truncated"])
def test_a_listing_it_cannot_trust_files_nothing(land, listing, cause):
    (land.home / "gh-list-answer").write_text(listing)
    refused(land.finish(), cause)
    assert land.issues() == []


def test_a_create_with_no_issue_url_fails(land):
    land.env["FAKE_GH_URL"] = "nothing useful"
    refused(land.finish(), "issue URL")
