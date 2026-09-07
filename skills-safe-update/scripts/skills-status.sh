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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# Unifying the lock + .extra-skills.json, the upstream tree/commit lookups
# (root-tree quirk included), and the per-repo cache all live in upstream.py —
# shared with safe-update.sh's extras sync. This just prints its report.
python3 "$SCRIPT_DIR/upstream.py" status --base "$BASE" --lock "$LOCK"
