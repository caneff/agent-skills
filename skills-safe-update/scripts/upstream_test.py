"""Tests for upstream.py: lock/extras loading, the gh-backed tree lookups,
`status_rows`, `sync_extras` and the CLI `main`, all over temp files with a
canned gh runner. No network."""
import io
import json
import os
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import upstream  # noqa: E402

HEAD_ARGS = ("api", "repos/acme/repo/commits/HEAD", "--jq", ".sha+\" \"+.commit.tree.sha")
TREES_ARGS = ("api", "repos/acme/repo/git/trees/headsha1234?recursive=1")
TARBALL_ARGS = ("api", "repos/acme/repo/tarball/headsha1234")


def _done(args, code=0, out=b""):
    return subprocess.CompletedProcess(args, code, stdout=out)


def _tarball(files, prefix="acme-repo-abc"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        root = tarfile.TarInfo(prefix)
        root.type = tarfile.DIRTYPE
        tf.addfile(root)
        for path, data in files.items():
            info = tarfile.TarInfo(f"{prefix}/{path}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeGh:
    """Canned gh runner: `responses` maps an args tuple to (code, stdout)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        code, out = self.responses.get(args, (1, b""))
        return _done(args, code, out)


def _happy_responses(tree_entries=None, tarball=b""):
    entries = tree_entries if tree_entries is not None else [
        {"path": "skills/foo", "type": "tree", "sha": "foosha"},
        {"path": "skills/foo/SKILL.md", "type": "blob", "sha": "blobsha"},
    ]
    return {
        HEAD_ARGS: (0, b"headsha1234 roottreeSHA\n"),
        TREES_ARGS: (0, json.dumps({"tree": entries}).encode()),
        TARBALL_ARGS: (0, tarball),
    }


@pytest.fixture
def gh_runner():
    """Install a FakeGh for the test and restore the real runner after."""
    installed = []

    def install(responses):
        fake = FakeGh(responses)
        installed.append(upstream.set_gh_runner(fake))
        return fake

    yield install
    if installed:
        upstream.set_gh_runner(installed[0])


@pytest.fixture
def files(tmp_path):
    lock = tmp_path / "lock.json"
    extras = tmp_path / "extras.json"
    lock.write_text(json.dumps({"skills": {"foo": {
        "sourceUrl": "https://github.com/acme/repo",
        "skillPath": "skills/foo/SKILL.md",
        "skillFolderHash": "abc123",
    }}}))
    extras.write_text(json.dumps(
        {"bar": {"repo": "acme/other", "path": "bar", "treeSha": "def456"}}))
    return str(lock), str(extras)


def test_load_items_reads_lock_skill_fields(files):
    items = upstream.load_items(*files)
    assert {"name": "foo", "owner": "acme", "repo": "repo",
            "dir": "skills/foo", "hash": "abc123", "tag": ""} in items


def test_load_items_merges_extra_tagged_and_orders_lock_first(files):
    items = upstream.load_items(*files)
    assert [i["name"] for i in items] == ["foo", "bar"]
    assert items[1] == {"name": "bar", "owner": "acme", "repo": "other",
                        "dir": "bar", "hash": "def456", "tag": " [extra]"}


def test_load_items_tolerates_missing_extras(files, tmp_path):
    assert [i["name"] for i in upstream.load_items(files[0], str(tmp_path / "nope.json"))] == ["foo"]


def test_load_items_non_github_source_has_no_owner(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"skills": {"x": {"sourceUrl": "https://example.com/a/b"}}}))
    [item] = upstream.load_items(str(lock), None)
    assert item["owner"] is None and item["repo"] is None


def test_prelock_lines_emit_name_tab_hash(files):
    assert upstream.prelock_lines(*files) == ["foo\tabc123", "bar\tdef456"]


def test_upstream_tree_seeds_root_head_and_dirs_not_blobs(gh_runner):
    gh_runner(_happy_responses())
    t = upstream.upstream_tree("acme", "repo", {})
    assert t["tree"][""] == "roottreeSHA"
    assert t["head"] == "headsha1234"
    assert t["tree"]["skills/foo"] == "foosha"
    assert "skills/foo/SKILL.md" not in t["tree"]


def test_failed_trees_call_keeps_root_and_marks_dirs_unknown(gh_runner):
    responses = _happy_responses()
    del responses[TREES_ARGS]
    gh_runner(responses)
    t = upstream.upstream_tree("acme", "repo", {})
    assert upstream.upstream_dir(t, "") == (True, "roottreeSHA")
    assert upstream.upstream_dir(t, "skills/foo") == (False, None)


def test_failed_commit_call_returns_none_and_is_cached(gh_runner):
    fake = gh_runner({})
    cache = {}
    assert upstream.upstream_tree("acme", "repo", cache) is None
    n = len(fake.calls)
    assert upstream.upstream_tree("acme", "repo", cache) is None
    assert len(fake.calls) == n


def test_cache_serves_second_lookup_with_no_new_call(gh_runner):
    fake = gh_runner(_happy_responses())
    cache = {}
    upstream.upstream_tree("acme", "repo", cache)
    n = len(fake.calls)
    upstream.upstream_tree("acme", "repo", cache)
    assert len(fake.calls) == n


def test_upstream_dir_missing_dir_is_known_and_none(gh_runner):
    gh_runner(_happy_responses())
    t = upstream.upstream_tree("acme", "repo", {})
    assert upstream.upstream_dir(t, "gone") == (True, None)


# --- status_rows -----------------------------------------------------------

def _git_repo(path, skills):
    """A repo whose HEAD holds each skill dir; returns {name: tree sha}."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}

    def git(*a):
        return subprocess.run(["git", *a], cwd=path, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    for name, content in skills.items():
        os.makedirs(os.path.join(path, name), exist_ok=True)
        with open(os.path.join(path, name, "SKILL.md"), "w") as f:
            f.write(content)
    git("add", "-A")
    git("commit", "-q", "-m", "x")
    return {name: git("rev-parse", f"HEAD:{name}") for name in skills}


def _lock(tmp_path, entries):
    p = tmp_path / "lock.json"
    p.write_text(json.dumps({"skills": entries}))
    return str(p)


def _entry(url, path, folder_hash):
    return {"sourceUrl": url, "skillPath": f"{path}/SKILL.md", "skillFolderHash": folder_hash}


def test_status_rows_classifies_every_state_and_sorts(tmp_path, monkeypatch, gh_runner):
    repo = tmp_path / "repo"
    repo.mkdir()
    local = _git_repo(str(repo), {"clean": "a", "edited": "b", "stale": "c",
                                  "both": "d", "orphan": "e", "nogh": "f"})
    monkeypatch.chdir(repo)
    url = "https://github.com/acme/repo"
    lock = _lock(tmp_path, {
        "clean": _entry(url, "clean", local["clean"]),
        "edited": _entry(url, "edited", "oldhash"),
        "stale": _entry(url, "stale", local["stale"]),
        "both": _entry(url, "both", "oldhash2"),
        "orphan": _entry(url, "orphan", local["orphan"]),
        "nogh": _entry("https://example.com/x/y", "nogh", local["nogh"]),
        "missing": _entry(url, "missing", "zzz"),
    })
    upstream_dirs = [
        {"path": "clean", "type": "tree", "sha": local["clean"]},
        {"path": "edited", "type": "tree", "sha": "oldhash"},
        {"path": "stale", "type": "tree", "sha": "newupstream"},
        {"path": "both", "type": "tree", "sha": "newupstream2"},
        {"path": "missing", "type": "tree", "sha": "zzz"},
    ]
    gh_runner(_happy_responses(upstream_dirs))
    rows = upstream.status_rows("HEAD", lock, str(tmp_path / "none.json"))
    assert rows == [
        ("EDITED+STALE (merge needed)", "both"),
        ("ORPHAN (removed upstream)", "orphan"),
        ("OUT OF DATE", "stale"),
        ("edited, on latest", "edited"),
        ("edited, on latest", "missing"),
        ("non-github source (skip)", "nogh"),
        ("clean", "clean"),
    ]


def test_status_rows_unknown_when_gh_fails(tmp_path, monkeypatch, gh_runner):
    repo = tmp_path / "repo"
    repo.mkdir()
    local = _git_repo(str(repo), {"a": "x"})
    monkeypatch.chdir(repo)
    lock = _lock(tmp_path, {"a": _entry("https://github.com/acme/repo", "a", local["a"])})
    gh_runner({})
    rows = upstream.status_rows("HEAD", lock, None)
    assert rows == [("upstream UNKNOWN (gh fetch failed)", "a")]


# --- sync_extras -----------------------------------------------------------

def _extras(tmp_path, entries):
    p = tmp_path / "extras.json"
    p.write_text(json.dumps(entries))
    return str(p)


def test_sync_extras_replaces_dir_and_rewrites_tree_sha(tmp_path, monkeypatch, gh_runner):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo").mkdir()
    (tmp_path / "foo" / "stale.txt").write_text("old")
    extras = _extras(tmp_path, {"foo": {"repo": "acme/repo", "path": "skills/foo", "treeSha": "old"}})
    tar = _tarball({"skills/foo/SKILL.md": b"new", "skills/foo/sub/x.txt": b"x",
                    "skills/other/SKILL.md": b"nope"})
    gh_runner(_happy_responses(tarball=tar))
    out = upstream.sync_extras(extras)
    assert out == ["  foo: synced from repo@headsha12"]
    assert (tmp_path / "foo" / "SKILL.md").read_bytes() == b"new"
    assert (tmp_path / "foo" / "sub" / "x.txt").read_bytes() == b"x"
    assert not (tmp_path / "foo" / "stale.txt").exists()
    assert not (tmp_path / "foo" / "other").exists()
    assert json.load(open(extras))["foo"]["treeSha"] == "foosha"


def test_sync_extras_skips_up_to_date_silently(tmp_path, monkeypatch, gh_runner):
    monkeypatch.chdir(tmp_path)
    extras = _extras(tmp_path, {"foo": {"repo": "acme/repo", "path": "skills/foo", "treeSha": "foosha"}})
    fake = gh_runner(_happy_responses())
    assert upstream.sync_extras(extras) == []
    assert TARBALL_ARGS not in fake.calls
    assert not (tmp_path / "foo").exists()


def test_sync_extras_reports_failed_fetch(tmp_path, monkeypatch, gh_runner):
    monkeypatch.chdir(tmp_path)
    extras = _extras(tmp_path, {"foo": {"repo": "acme/repo", "path": "skills/foo", "treeSha": "old"}})
    gh_runner({})
    assert upstream.sync_extras(extras) == ["  foo: upstream fetch failed, skipped"]


def test_sync_extras_reports_orphan(tmp_path, monkeypatch, gh_runner):
    monkeypatch.chdir(tmp_path)
    extras = _extras(tmp_path, {"foo": {"repo": "acme/repo", "path": "gone", "treeSha": "old"}})
    gh_runner(_happy_responses())
    assert upstream.sync_extras(extras) == ["  foo: path 'gone' gone upstream (ORPHAN), skipped"]


def test_sync_extras_failed_tarball_keeps_existing_dir(tmp_path, monkeypatch, gh_runner):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo").mkdir()
    (tmp_path / "foo" / "keep.txt").write_text("keep")
    extras = _extras(tmp_path, {"foo": {"repo": "acme/repo", "path": "skills/foo", "treeSha": "old"}})
    responses = _happy_responses()
    del responses[TARBALL_ARGS]
    gh_runner(responses)
    assert upstream.sync_extras(extras) == ["  foo: tarball fetch failed, skipped"]
    assert (tmp_path / "foo" / "keep.txt").exists()
    assert json.load(open(extras))["foo"]["treeSha"] == "old"


# --- main ------------------------------------------------------------------

def test_main_prelock_prints_lines(files, capsys):
    assert upstream.main(["prelock", "--lock", files[0], "--extras", files[1]]) == 0
    assert capsys.readouterr().out == "foo\tabc123\nbar\tdef456\n"


def test_main_status_prints_padded_rows(tmp_path, monkeypatch, gh_runner, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    local = _git_repo(str(repo), {"a": "x"})
    monkeypatch.chdir(repo)
    lock = _lock(tmp_path, {"a": _entry("https://github.com/acme/repo", "a", local["a"])})
    gh_runner(_happy_responses([{"path": "a", "type": "tree", "sha": local["a"]}]))
    assert upstream.main(["status", "--base", "HEAD", "--lock", lock,
                          "--extras", str(tmp_path / "none.json")]) == 0
    assert capsys.readouterr().out == f"{'a':<32}clean\n"


def test_main_sync_extras_prints_report(tmp_path, monkeypatch, gh_runner, capsys):
    monkeypatch.chdir(tmp_path)
    extras = _extras(tmp_path, {"foo": {"repo": "acme/repo", "path": "gone", "treeSha": "old"}})
    gh_runner(_happy_responses())
    assert upstream.main(["sync-extras", "--extras", extras]) == 0
    assert "foo: path 'gone' gone upstream" in capsys.readouterr().out


def test_main_without_command_prints_help_and_exits_2(capsys):
    assert upstream.main([]) == 2
    assert "usage:" in capsys.readouterr().out


def test_selfcheck_mode_is_removed(capsys):
    with pytest.raises(SystemExit) as exc:
        upstream.main(["--selfcheck"])
    assert exc.value.code == 2
    assert "--selfcheck" in capsys.readouterr().err
