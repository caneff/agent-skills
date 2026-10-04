#!/usr/bin/env bash
# The permission rules `flow/claude/settings.json` must hold, by name.
# Run: bash flow/settings-rules.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
settings="$here/claude/settings.json"
fails=0
has() { # has <list: allow|ask> <rule>
  if jq -e --arg l "$1" --arg r "$2" '.permissions[$l] | index($r)' "$settings" >/dev/null 2>&1
  then echo "PASS: permissions.$1 holds $2"
  else echo "FAIL: permissions.$1 has no $2"; fails=1; fi
}
lacks() { # lacks <list> <rule>
  if jq -e --arg l "$1" --arg r "$2" '.permissions[$l] | index($r)' "$settings" >/dev/null 2>&1
  then echo "FAIL: permissions.$1 still holds $2"; fails=1
  else echo "PASS: permissions.$1 dropped $2"; fi
}

# The live e2e lock (#1392): each way an agent starts twitch-rules-scroller's
# ./e2e.sh is an `ask` rule, since it takes over Chris's monitor. A rule that no
# start form matches does not stop it, so the forms are named here, `job-run`
# and `bash -c` included: `Bash(job-run:*)` is allowed, so an unmatched
# `job-run -- ./e2e.sh` would start with no prompt.
for rule in 'Bash(./e2e.sh *)' 'Bash(bash e2e.sh *)' 'Bash(bash ./e2e.sh *)' \
            'Bash(/home/caneff/src/twitch-rules-scroller/e2e.sh *)' \
            'Bash(bash /home/caneff/src/twitch-rules-scroller/e2e.sh *)' \
            'Bash(*/.claude/worktrees/*/e2e.sh *)' 'Bash(bash */.claude/worktrees/*/e2e.sh *)' \
            'Bash(job-run *e2e.sh*)' 'Bash(bash -c *e2e.sh*)' 'Bash(sh -c *e2e.sh*)'; do
  has ask "$rule"
done

# Compute pre-authorization, ruled by Chris 2026-09-28 (#1225): `uv run` and
# `job-run`, with the narrower `uv run` paths it makes redundant gone.
has allow 'Bash(uv run:*)'
has allow 'Bash(job-run:*)'
for rule in 'Bash(uv run finders/*)' \
            'Bash(uv run --with google-auth --with requests tools/upton_links/sheet/write_rules.py:*)' \
            'Bash(uv run tools/upton_links/make_links.py:*)' 'Bash(uv run tools/upton_links/make_big.py:*)'; do
  lacks allow "$rule"
done

# The install check runs at every session start (#1397): a settings.json that
# stopped being the link drifted for 30 minutes unseen, long after install.sh.
if jq -e '[.hooks.SessionStart[].hooks[].command] | any(test("install-check\\.sh --quiet"))' "$settings" >/dev/null 2>&1
then echo "PASS: SessionStart runs install-check.sh --quiet"
else echo "FAIL: no SessionStart hook runs install-check.sh --quiet"; fails=1; fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
