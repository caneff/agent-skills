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
# (twitch-rules-scroller #1131): only an e2e.sh run carrying --main-monitor is
# an `ask` rule, since that run takes over Chris's monitor; a virtual-monitor
# run needs no go. Anchored at the start of a subcommand (#1725): a leading `*`
# matched `e2e.sh` and `--main-monitor` anywhere in a command, so a heredoc
# quoting a repo's AGENTS.md was denied in a `-p` run. Asserted by behaviour:
# samples are matched against permissions.ask the way the harness matches a
# Bash rule (code.claude.com/docs/en/permissions: `*` = any text, the rule must
# match the whole subcommand). This models one subcommand; it does not split
# compound commands on `&&`, `;`, `|` or newlines as the harness does first,
# so a sample is one already-split subcommand (the heredoc is one command).
e2e_check=$(jq -c '.permissions.ask' "$settings" 2>&1 | python3 -c '
import fnmatch, json, sys
ask = json.loads(sys.stdin.read())
patterns = [r[5:-1] for r in ask if r.startswith("Bash(") and r.endswith(")")]
def matches(cmd):
    return [p for p in patterns if fnmatch.fnmatchcase(cmd, p)]
tw = "/home/caneff/src/twitch-rules-scroller"
wt = tw + "/.claude/worktrees/implement-9/e2e.sh"
wt2 = "/home/caneff/src/.claude/worktrees/twitch-rules-scroller/implement-9/e2e.sh"
# (start of the command, text that closes it): the -c forms open a quote
starts = [(h, "") for h in ("./e2e.sh", "bash e2e.sh", "bash ./e2e.sh", "sh e2e.sh", "sh ./e2e.sh",
                            tw + "/e2e.sh", "bash " + tw + "/e2e.sh", wt, "bash " + wt, wt2,
                            "bash " + wt2, "job-run --name x ./e2e.sh")]
starts += [("bash -c \"./e2e.sh", "\""), ("sh -c \"./e2e.sh", "\"")]
bad = []
for head, close in starts:
    for tail, want in ((" --main-monitor", True), (" --only foo --main-monitor", True),
                       ("", False), (" --only foo", False)):
        cmd = head + tail + close
        if bool(matches(cmd)) != want:
            bad.append(("should match" if want else "must not match") + ": " + cmd)
# The 2026-11-13 denial: e2e.sh ~4.7k chars into a heredoc, --main-monitor ~9k
# chars after it (the sizes only make the sample as long as the real one).
heredoc = "cat > f <<\x27PY\x27\n" + "x" * 4600 + " ./e2e.sh --only x " + "y" * 9000 + " --main-monitor\nPY"
for cmd in (heredoc, "echo e2e.sh --main-monitor", "grep -n e2e.sh AGENTS.md; echo --main-monitor"):
    if matches(cmd):
        bad.append("must not match: " + cmd[:40].replace("\n", " "))
bad += ["rule starts with *: " + r for r in ask if r.startswith("Bash(*")]
if bad: print("\n".join(bad))
' 2>&1; echo "rc=$?")
if [ "$e2e_check" = "rc=0" ]
then echo "PASS: ask rules match every e2e.sh --main-monitor start form and nothing else, none starts with *"
else echo "FAIL: e2e ask rules:"; echo "$e2e_check"; fails=1; fi

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
