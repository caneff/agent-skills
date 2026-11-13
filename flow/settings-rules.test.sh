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

# The live e2e lock (#1392), narrowed by Chris's ruling 2026-11-09
# (twitch-rules-scroller #1131): only an e2e.sh command line carrying
# --main-monitor is an `ask` rule, since that run takes over Chris's monitor; a
# virtual-monitor run needs no go. One pattern covers every start form. It is
# the only ask rule that names e2e.sh: any other, however broad, would prompt a
# virtual-monitor run, and the ten per-form rules it replaced stay gone.
has ask 'Bash(*e2e.sh*--main-monitor*)'
for rule in 'Bash(./e2e.sh *)' 'Bash(bash e2e.sh *)' 'Bash(bash ./e2e.sh *)' \
            'Bash(/home/caneff/src/twitch-rules-scroller/e2e.sh *)' \
            'Bash(bash /home/caneff/src/twitch-rules-scroller/e2e.sh *)' \
            'Bash(*/.claude/worktrees/*/e2e.sh *)' 'Bash(bash */.claude/worktrees/*/e2e.sh *)' \
            'Bash(job-run *e2e.sh*)' 'Bash(bash -c *e2e.sh*)' 'Bash(sh -c *e2e.sh*)'; do
  lacks ask "$rule"
done
others=$(jq -r '.permissions.ask[] | select(contains("e2e.sh") and . != "Bash(*e2e.sh*--main-monitor*)")' "$settings" 2>&1)
if [ $? = 0 ] && [ -z "$others" ]
then echo "PASS: permissions.ask holds no other e2e.sh rule"
else echo "FAIL: permissions.ask holds another e2e.sh rule (or jq failed): $others"; fails=1; fi

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
