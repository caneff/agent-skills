#!/usr/bin/env python3
"""Shared upstream-tree lookups for safe-update.sh and skills-status.sh.

Owns: reading `.skill-lock.json` + `.extra-skills.json` into one item list,
the two `gh api` calls that resolve a repo's head commit and tree map, and a
per-repo cache so a repo's tree is fetched at most once per invocation.

Root-tree quirk: `gh api repos/<repo>/git/trees/<sha>?recursive=1` never
lists the repo root itself (needed for a skill living at the repo's top
level, dir==""), and the *response's own* `.sha` field is the commit sha,
not a tree sha, so it can't fill the gap either. The root entry is seeded
instead from `commits/HEAD`'s `.commit.tree.sha`, fetched in the same call
that gets the head commit sha.

Subcommands: `status` (skills-status.sh's report), `prelock` (safe-update.sh's
pre-update hash dump), `sync-extras` (safe-update.sh's hand-installed-skill
sync). Tests: `upstream_test.py`.
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile


def _default_gh_runner(*args):
    return subprocess.run(("gh",) + args, capture_output=True)


# Every `gh api` call in this module goes through this one indirection, so
# tests can swap in canned responses instead of touching the network.
_gh_runner = _default_gh_runner


def set_gh_runner(fn):
    """Install a replacement gh runner; returns the previous one."""
    global _gh_runner
    prev = _gh_runner
    _gh_runner = fn
    return prev


def gh(*args):
    return _gh_runner(*args)


def load_items(lock_path, extras_path):
    """Read the lockfile and .extra-skills.json into one unified item list.

    Each item: {"name", "owner", "repo", "dir", "hash", "tag"}. `owner`/`repo`
    are None when a lock entry's sourceUrl isn't a recognizable github URL.
    Lock items come first, then extras, each tagged " [extra]".
    """
    items = []
    if lock_path and os.path.exists(lock_path):
        lock = json.load(open(lock_path)).get("skills", {})
        for name, e in lock.items():
            m = re.search(r"github\.com[:/]+([^/]+)/([^/.]+)", e.get("sourceUrl", ""))
            skill_dir = re.sub(r"/SKILL\.md$", "", e.get("skillPath", ""))
            owner, repo = m.groups() if m else (None, None)
            items.append({
                "name": name, "owner": owner, "repo": repo,
                "dir": skill_dir, "hash": e.get("skillFolderHash", ""), "tag": "",
            })
    if extras_path and os.path.exists(extras_path):
        extras = json.load(open(extras_path))
        for name, e in extras.items():
            owner, repo = e["repo"].split("/", 1)
            items.append({
                "name": name, "owner": owner, "repo": repo,
                "dir": e.get("path", ""), "hash": e.get("treeSha", ""), "tag": " [extra]",
            })
    return items


def prelock_lines(lock_path, extras_path):
    """name<TAB>installed-upstream-hash for every item, lock then extras."""
    return [f"{it['name']}\t{it['hash']}" for it in load_items(lock_path, extras_path)]


def commit_head(owner, repo):
    """Return (head sha, root tree sha) for a repo's default branch, or None."""
    r = gh("api", f"repos/{owner}/{repo}/commits/HEAD", "--jq", ".sha+\" \"+.commit.tree.sha")
    if r.returncode != 0:
        return None
    head, root_tree = r.stdout.decode().split()
    return head, root_tree


def upstream_tree(owner, repo, cache):
    """{"head": sha, "tree": {"<dir-in-repo>": tree-sha, ...}} or None on failure.

    `cache` is a dict the caller keeps across calls so a repo already looked
    up this invocation isn't fetched twice.
    """
    key = (owner, repo)
    if key in cache:
        return cache[key]
    ch = commit_head(owner, repo)
    if ch is None:
        cache[key] = None
        return None
    head, root_tree = ch
    tree = {"": root_tree}
    # The root entry never needs the recursive trees call (the old inline
    # code skipped it for root-path extras); a failed trees call only makes
    # the non-root dirs unknown, so it is recorded rather than fatal.
    r = gh("api", f"repos/{owner}/{repo}/git/trees/{head}?recursive=1")
    trees_failed = r.returncode != 0
    if not trees_failed:
        for t in json.loads(r.stdout).get("tree", []):
            if t["type"] == "tree":
                tree[t["path"]] = t["sha"]
    result = {"head": head, "tree": tree, "trees_failed": trees_failed}
    cache[key] = result
    return result


def upstream_dir(t, path):
    """(known, sha) for `path` in an `upstream_tree` result: the root ("")
    is always known; other dirs are unknown when the trees call failed."""
    if path == "":
        return True, t["tree"][""]
    if t["trees_failed"]:
        return False, None
    return True, t["tree"].get(path)


def status_rows(base, lock_path, extras_path):
    """[(status, display-name), ...] sorted the way skills-status.sh prints them."""
    items = load_items(lock_path, extras_path)
    cache = {}
    rows = []
    for it in items:
        r = subprocess.run(["git", "rev-parse", f"{base}:{it['name']}"], capture_output=True, text=True)
        local = r.stdout.strip() if r.returncode == 0 else "MISSING"
        if not it["owner"]:
            status = "non-github source (skip)"
        else:
            t = upstream_tree(it["owner"], it["repo"], cache)
            known, upstream = (False, None) if t is None else upstream_dir(t, it["dir"])
            if not known:
                status = "upstream UNKNOWN (gh fetch failed)"
            else:
                folder_hash = it["hash"]
                edited = local != folder_hash
                if upstream is None:
                    status = "ORPHAN (removed upstream)"
                elif edited and folder_hash != upstream:
                    status = "EDITED+STALE (merge needed)"
                elif edited:
                    status = "edited, on latest"
                elif folder_hash != upstream:
                    status = "OUT OF DATE"
                else:
                    status = "clean"
        rows.append((status, it["name"] + it["tag"]))
    order = {"clean": 9, "non-github source (skip)": 8}
    rows.sort(key=lambda r: (order.get(r[0], 0), r[0], r[1]))
    return rows


def sync_extras(extras_path):
    """Sync every hand-installed skill in .extra-skills.json from its github
    upstream; rewrites the manifest's treeSha for whatever it updates.
    Returns the report lines (mirrors the old inline script's prints)."""
    manifest = json.load(open(extras_path))
    cache = {}
    out = []
    for name, e in manifest.items():
        owner, repo = e["repo"].split("/", 1)
        path = e.get("path", "")
        t = upstream_tree(owner, repo, cache)
        known, up = (False, None) if t is None else upstream_dir(t, path)
        if not known:
            out.append(f"  {name}: upstream fetch failed, skipped")
            continue
        if not up:
            out.append(f"  {name}: path {path!r} gone upstream (ORPHAN), skipped")
            continue
        if up == e.get("treeSha"):
            continue
        r = gh("api", f"repos/{owner}/{repo}/tarball/{t['head']}")
        if r.returncode != 0:
            out.append(f"  {name}: tarball fetch failed, skipped")
            continue
        tf = tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r:gz")
        prefix = tf.getmembers()[0].name.split("/")[0]
        want = f"{prefix}/{path}".rstrip("/") + "/"
        if os.path.isdir(name):
            shutil.rmtree(name)  # reversible: caller's git buffer holds the old version
        for mem in tf.getmembers():
            if not mem.isfile() or not mem.name.startswith(want) or ".." in mem.name:
                continue
            dest = os.path.join(name, mem.name[len(want):])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(tf.extractfile(mem).read())
        e["treeSha"] = up
        out.append(f"  {name}: synced from {repo}@{t['head'][:9]}")
    with open(extras_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return out


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("status", help="print skills-status.sh's report")
    sp.add_argument("--base", required=True, help="git rev/tree to read local skill hashes from")
    sp.add_argument("--lock", required=True, help="path to .skill-lock.json")
    sp.add_argument("--extras", default=".extra-skills.json")

    sp = sub.add_parser("prelock", help="dump name<TAB>hash for every tracked skill")
    sp.add_argument("--lock", required=True)
    sp.add_argument("--extras", default=".extra-skills.json")

    sp = sub.add_parser("sync-extras", help="sync hand-installed skills from their upstreams")
    sp.add_argument("--extras", required=True)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "status":
        for status, name in status_rows(args.base, args.lock, args.extras):
            print(f"{name:<32}{status}")
    elif args.cmd == "prelock":
        for line in prelock_lines(args.lock, args.extras):
            print(line)
    elif args.cmd == "sync-extras":
        for line in sync_extras(args.extras):
            print(line)
    else:
        build_parser().print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
