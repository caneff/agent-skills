#!/bin/bash
# Teaching hook (PreToolUse, Bash): `gh issue create` answers, once per
# session, with WORKFLOW.md § Before filing a ticket and the open issues whose
# title matches the new ticket's component, from a search this hook runs.
# Shared mechanics: teach-lib.sh.
#
# The component is the title's text before its first ": " (the shape most
# titles here take, `merge-cleanup: ...`), else its first identifier-shaped
# word (one holding `.`, `_`, `-` or `/`). The repo is the command's own
# `--repo`/`-R`, else the origin of the directory the command files from (a
# `cd` earlier in the line, else the session's cwd). The search covers open
# issue titles only in that one repo, and the context names both.

# shellcheck source=teach-lib.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh"

runs gh issue create || teach_emit
teach WORKFLOW.md "Before filing a ticket" "\`gh issue create\` files a ticket" || teach_emit

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

# The repo: a flag on the create command itself (looked for in its unquoted
# words, so a `-R` inside a quoted body is not taken), else the origin of the
# directory it files from.
if [[ "$create" =~ (^|[[:space:]])(--repo|-R)([= ]|$) ]]; then
  repo=$(flag_value '--repo|-R')
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
    *github.com*) repo=${origin#*github.com}; repo=${repo#[:/]}; repo=${repo%/}; repo=${repo%.git} ;;
    *) repo="" ;;
  esac
fi
if [ -z "$repo" ]; then
  teach_add "No repo could be read from this command (no \`--repo\`, and no GitHub origin for the directory it runs in), so no search ran for open issues on \`$component\`."
  teach_emit
fi

# Bounded under the hook's own 15 s timeout, so a slow gh is reported here
# rather than the hook being killed with nothing said.
shown_search="gh issue list --repo $repo --state open --search \"$component in:title\""
if ! found=$(timeout 10 gh issue list --repo "$repo" --state open --search "$component in:title" --limit 20 \
               --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>&1); then
  teach_add "The search for open issues on \`$component\` in $repo failed, so it says nothing about duplicates ($shown_search): ${found:-timed out after 10 s}"
elif [ -z "$found" ]; then
  teach_add "No open issue's title in $repo matches \`$component\` ($shown_search; titles only, not bodies)."
else
  teach_add "Open issues in $repo whose title matches \`$component\` ($shown_search; titles only, first 20):"$'\n'"$found"
fi
teach_emit
