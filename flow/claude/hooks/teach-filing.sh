#!/bin/bash
# Teaching hook (PreToolUse, Bash): `gh issue create` answers, once per
# session, with WORKFLOW.md § Before filing a ticket and the open issues whose
# title matches the new ticket's component, from a search this hook runs.
# Shared mechanics: teach-lib.sh.
#
# The component is the title's text before its first ": " (the shape most
# titles here take, `merge-cleanup: ...`), else its first identifier-shaped
# word (one holding `.`, `_`, `-` or `/`). The search covers open issue
# titles only, and the context says so.

# Cheap exit before any parsing: most Bash calls are not a gh issue create.
input=$(cat)
case "$input" in *gh*issue*create*) ;; *) exit 0 ;; esac

# shellcheck source=teach-lib.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh" <<< "$input"

runs gh issue create || teach_emit
teach WORKFLOW.md "Before filing a ticket" "\`gh issue create\` files a ticket" || teach_emit

# A flag's value from the command, quoted or bare: flag_value <regex of names>.
flag_value() {
  local pre="(^|[[:space:]])($1)[= ]+"
  if [[ "$TEACH_SCAN" =~ $pre\"([^\"]*)\" ]] || [[ "$TEACH_SCAN" =~ $pre\'([^\']*)\' ]] \
     || [[ "$TEACH_SCAN" =~ $pre([^[:space:]\"\']+) ]]; then
    printf '%s' "${BASH_REMATCH[3]}"
  fi
}
title=$(flag_value '--title|-t')
repo=$(flag_value '--repo|-R')
if [[ "$title" == *": "* ]]; then
  component=${title%%: *}
else
  component=$(printf '%s\n' "$title" | tr -s '[:space:]' '\n' | grep -m1 -E '^[A-Za-z0-9]+[._/-][A-Za-z0-9._/-]*$')
fi

if [ -z "$component" ]; then
  teach_add "No component could be read from this command's title, so no search ran for open issues on the same component."
  teach_emit
fi

search=(issue list ${repo:+--repo "$repo"} --state open --search "$component in:title" --limit 20
        --json number,title --jq '.[] | "#\(.number) \(.title)"')
shown_search="gh issue list${repo:+ --repo $repo} --state open --search \"$component in:title\""
if ! found=$(cd "${TEACH_CWD:-.}" 2>/dev/null && gh "${search[@]}" 2>&1); then
  teach_add "The search for open issues on \`$component\` failed, so it says nothing about duplicates ($shown_search): $found"
elif [ -z "$found" ]; then
  teach_add "No open issue's title matches \`$component\` ($shown_search; titles only, not bodies)."
else
  teach_add "Open issues whose title matches \`$component\` ($shown_search; titles only, first 20):"$'\n'"$found"
fi
teach_emit
