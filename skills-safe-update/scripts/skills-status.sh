#!/usr/bin/env bash
# Read-only status for installed skills. Distinguishes the two ways a skill can
# "differ from origin", which the lockfile alone can't tell apart:
#
#   edited, on latest  — your edits sit on top of the CURRENT upstream
#   OUT OF DATE        — upstream moved past the version you installed
#   EDITED+STALE       — your edits sit on an OLD upstream (update => manual merge)
#   ORPHAN             — installed but gone from upstream (renamed/removed)
#
# Three hashes per skill, two independent comparisons:
#   local    = git tree SHA of your working copy
#   lock     = skillFolderHash in the lockfile (the upstream version you installed FROM)
#   upstream = current tree SHA of that folder in the source repo
# local != lock  => you edited it.   lock != upstream => upstream moved.
#
# Covers lockfile skills AND hand-installed skills registered in
# .extra-skills.json (name -> {repo, path, treeSha}); extras print an [extra] tag.
#
# Pairs with safe-update.sh: this only REPORTS (mutates nothing); run it before
# updating to see what's stale and what'll need a hand-merge. Needs git + gh + python3.
set -euo pipefail
SKILLS="${SKILLS_DIR:-$HOME/.agents/skills}"
LOCK="${SKILL_LOCK:-$(dirname "$SKILLS")/.skill-lock.json}"
cd "$SKILLS"
[ -f "$LOCK" ] || { echo "no lockfile at $LOCK"; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "$SKILLS is not a git repo — run safe-update.sh once to init the buffer"; exit 1; }

# Tree SHA of the live working copy WITHOUT mutating anything: `stash create`
# makes a dangling commit of the current worktree (empty when clean → use HEAD),
# touching neither the index nor the working tree.
WT=$(git stash create 2>/dev/null || true)
BASE="${WT:-HEAD}"

BASE="$BASE" LOCK="$LOCK" python3 - <<'PY'
import json, os, re, subprocess, sys

base = os.environ["BASE"]
lock = json.load(open(os.environ["LOCK"])).get("skills", {})
extra = json.load(open(".extra-skills.json")) if os.path.exists(".extra-skills.json") else {}

def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)

# Fetch each source repo's full tree once (default branch); cache dir->sha maps.
_cache = {}
def upstream_map(owner, repo):
    key = (owner, repo)
    if key not in _cache:
        r = sh("gh", "api", f"repos/{owner}/{repo}/git/trees/HEAD?recursive=1")
        # "" = repo root, for a skill living at the repo top level. The trees API
        # echoes the resolved COMMIT sha as .sha, so take the root tree from the
        # commits API instead.
        r2 = sh("gh", "api", f"repos/{owner}/{repo}/commits/HEAD", "--jq", ".commit.tree.sha")
        if r.returncode == 0 and r2.returncode == 0:
            m = {"": r2.stdout.strip()}
            for t in json.loads(r.stdout).get("tree", []):
                if t["type"] == "tree":
                    m[t["path"]] = t["sha"]
        else:
            m = None  # fetch failed → staleness UNKNOWN
        _cache[key] = m
    return _cache[key]

# Unify both sources into (name, (owner,repo)|None, dir-in-repo, installed-hash, tag).
items = []
for name, e in lock.items():
    m = re.search(r"github\.com[:/]+([^/]+)/([^/.]+)", e.get("sourceUrl", ""))
    skill_dir = re.sub(r"/SKILL\.md$", "", e.get("skillPath", ""))  # skills/<cat>/<name>
    items.append((name, m.groups() if m else None, skill_dir, e.get("skillFolderHash", ""), ""))
for name, e in extra.items():
    items.append((name, tuple(e["repo"].split("/", 1)), e.get("path", ""), e.get("treeSha", ""), " [extra]"))

rows = []
for name, src, skill_dir, folder_hash, tag in items:
    r = sh("git", "rev-parse", f"{base}:{name}")
    local = r.stdout.strip() if r.returncode == 0 else "MISSING"

    if not src:
        status = "non-github source (skip)"
    else:
        up = upstream_map(*src)
        if up is None:
            status = "upstream UNKNOWN (gh fetch failed)"
        else:
            upstream = up.get(skill_dir)
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
    rows.append((status, name + tag))

# Group: actionable rows first, clean last.
order = {"clean": 9, "non-github source (skip)": 8}
rows.sort(key=lambda r: (order.get(r[0], 0), r[0], r[1]))
for status, name in rows:
    print(f"{name:<32}{status}")
PY
