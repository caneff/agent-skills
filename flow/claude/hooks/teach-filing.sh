#!/bin/bash
# Teaching hook (PreToolUse, Bash): `gh issue create` answers with the open
# issues whose title matches the new ticket's component, from a search this
# hook runs on every filing, and, once per session, with WORKFLOW.md § Before
# filing a ticket.
# Shared mechanics: teach-lib.sh.
#
# The component is the title's text before its first ": " (the shape most
# titles here take, `merge-cleanup: ...`), else its first identifier-shaped
# word (one holding `.`, `_`, `-` or `/`). The repo is the command's own
# `--repo`/`-R`, else a `GH_REPO=` prefix on it, else the origin of the
# directory the command files from (a `cd` earlier in the line, else the
# session's cwd): the order gh itself reads them in. The search covers open
# issue titles only in that one repo, and the context names both.

# shellcheck source=teach-lib.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh" 2>/dev/null || {
  printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "Teaching hook error: teach-lib.sh is missing beside teach-filing.sh, so it cannot teach."}}'
  exit 0
}

runs gh issue create || teach_emit
# The section once per session; the search below on every filing, since its
# matches belong to the ticket being filed (#1409 story 6).
teach WORKFLOW.md "Before filing a ticket" "\`gh issue create\` files a ticket"

# The `gh issue create` command as the shell runs it (quoted text dropped),
# and the unquoted directory of the last `cd` before it.
create=$(printf '%s\n' "$TEACH_RUN" | grep -m1 -E '^gh[[:space:]]+issue[[:space:]]+create')
cd_arg=$(printf '%s\n' "$TEACH_RUN" | sed -nE '/^gh[[:space:]]+issue[[:space:]]+create/q; s/^cd([[:space:]]+([^[:space:]]*))?([[:space:]].*)?$/=\2/p' | tail -1)

# A flag's value from the command, quoted or bare: flag_value <regex of names>.
flag_value() {
  local pre="(^|[[:space:]])($1)[= ]+"
  if [[ "$TEACH_SCAN" =~ $pre\"([^\"]*)\" ]] || [[ "$TEACH_SCAN" =~ $pre\'([^\']*)\' ]] \
     || [[ "$TEACH_SCAN" =~ $pre([^[:space:]\"\']+) ]]; then
    printf '%s' "${BASH_REMATCH[3]}"
  fi
}
title=$(flag_value '--title|-t')
if [[ "$title" == *": "* ]]; then
  component=${title%%: *}
else
  component=$(printf '%s\n' "$title" | tr -s '[:space:]' '\n' | grep -m1 -E '^[A-Za-z0-9]+[._/-][A-Za-z0-9._/-]*$')
fi
if [ -z "$component" ]; then
  teach_add "No component could be read from this command's title, so no search ran for open issues on the same component."
  teach_emit
fi

# github_repo <origin or GH_REPO value>: its owner/name, or nothing.
github_repo() {
  local r
  case "$1" in
    *github.com*) r=${1#*github.com}; r=${r#[:/]}; r=${r%/}; printf '%s' "${r%.git}" ;;
    */*) printf '%s' "$1" ;;
  esac
}

# The repo: a flag on the create command itself, else a GH_REPO prefix, else
# the origin of the directory it files from. The flag is read from the
# command's unquoted words, so a `-R` inside a quoted body is never taken; only
# a quoted value (`--repo "o/r"`) is read from the quoted text.
gh_repo_re='(^|[[:space:];&|(])GH_REPO=([^[:space:]]+)[[:space:]]+([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*gh[[:space:]]+issue[[:space:]]+create'
bare_repo_re='(^|[[:space:]])(--repo|-R)[= ]+([^[:space:]-][^[:space:]]*)'
any_repo_re='(^|[[:space:]])(--repo|-R)([= ]|$)'
if [[ "$create" =~ $bare_repo_re ]]; then
  repo=${BASH_REMATCH[3]}
elif [[ "$create" =~ $any_repo_re ]]; then
  repo=$(flag_value '--repo|-R')
elif [[ "$BARE" =~ $gh_repo_re ]]; then
  repo=$(github_repo "${BASH_REMATCH[2]}")
else
  dir=$TEACH_CWD
  if [ -n "$cd_arg" ]; then
    dir=${cd_arg#=}
    case "$dir" in
      "") dir="" ;;
      "~"|"~/"*) dir="$HOME${dir#\~}" ;;
      /*) ;;
      *) dir="$TEACH_CWD/$dir" ;;
    esac
  fi
  origin=$([ -n "$dir" ] && git -C "$dir" remote get-url origin 2>/dev/null)
  case "$origin" in
    *github.com*) repo=$(github_repo "$origin") ;;
    *) repo="" ;;
  esac
fi
if [ -z "$repo" ]; then
  teach_add "No repo could be read from this command (no \`--repo\`, and no GitHub origin for the directory it runs in), so no search ran for open issues on \`$component\`."
  teach_emit
fi

# Bounded under the hook's own 15 s timeout, so a slow gh is reported here
# rather than the hook being killed with nothing said. One copy of the
# command: the part shown is the part run. gh's stderr is kept apart, so a
# warning on a good search is never read as a match.
search=(gh issue list --repo "$repo" --state open --search "$component in:title")
shown_search=$(printf '%q ' "${search[@]}"); shown_search=${shown_search% }
err=$(mktemp) || err=/dev/null
found=$(timeout 10 "${search[@]}" --limit 20 --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>"$err")
rc=$?
why=$(cat "$err" 2>/dev/null); [ "$err" = /dev/null ] || rm -f "$err"
if [ "$rc" -ne 0 ]; then
  case $rc in
    124) why="timed out after 10 s" ;;
    *) why="exited $rc${why:+: $why}" ;;
  esac
  teach_add "The search for open issues on \`$component\` in $repo failed, so it says nothing about duplicates ($shown_search): $why"
elif [ -z "$found" ]; then
  teach_add "No open issue's title in $repo matches \`$component\` ($shown_search; titles only, not bodies)."
else
  teach_add "Open issues in $repo whose title matches \`$component\` ($shown_search; titles only, first 20):"$'\n'"$found"
fi
teach_emit
