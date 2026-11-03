# Sourced, never run: moves WSL_INTEROP off a dead socket (#1625). A process
# tree outliving its Windows session keeps a WSL_INTEROP whose socket is gone,
# and every Windows call from it then lands in session 0 with no error: nothing
# appears on the desktop and the clipboard reads empty.
#
# Two carriers: `env.BASH_ENV` in claude/settings.json reaches a Claude Code
# Bash tool call and `!` command, which skip ~/.bashrc's interactive part, and
# the line flow/install.sh appends to ~/.bashrc reaches a new herdr pane shell.
# flow/install-check.sh names either one missing.
#
# BASH_ENV runs this before every non-interactive bash, including `bash -u`
# scripts and ones whose stdout or stdin is another program's. So it prints
# nothing, survives -u, keeps stdin from its probes, leaves no name behind. Bash
# does not apply -e while it reads this file, so a failed test here is harmless.
#
# What each case costs:
# - WSL_INTEROP is a socket: one file test, no Windows process. A live socket
#   reaching session 0 stays, since telling that takes a Windows process.
# - Dead or unset (both land in session 0, measured 2026-11-03), a socket
#   already found this boot: one file read, no Windows process.
# - Otherwise it asks PowerShell for the session behind each socket under
#   /run/WSL, newest first, and takes the first non-zero one: session 0 is
#   Windows' services session and every other is a user's. A liveness test
#   cannot choose here: of seven live sockets, three reached session 0.
#   Each probe gets 2 s (0.25 s measured) and all of them 3 s, plus 1 s to kill
#   a probe ignoring its timeout, so the most a shell waits is 4 s. That stays
#   under the shortest hook timeout, 5 s, so a hook is never killed in here.
# - Nothing found: the variable stays as it was and the command runs unchanged.
#   The record holds that verdict so later shells skip the wait:
#   `no-user-session` when every socket answered, for 60 s, and `unanswered`
#   when a probe failed or time ran out, for 10 s, since the next try may work.
#   Shells started together each probe; that costs one probe each, and no lock.
#
# The record is `<epoch> <socket or verdict>`, in the runtime tmpfs because a
# socket's path means nothing after a WSL restart. The WSL_INTEROP_* overrides
# are the test's seams.
__wsl_interop_repoint() {
  [ -S "${WSL_INTEROP:-}" ] && return 0
  local socket_dir="${WSL_INTEROP_SOCKET_DIR:-/run/WSL}"
  [ -d "$socket_dir" ] || return 0
  local powershell="${WSL_INTEROP_POWERSHELL:-/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe}"
  local record="${WSL_INTEROP_RECORD_DIR:-${XDG_RUNTIME_DIR:-/run/user/$UID}}/wsl-interop-repoint"
  local stamp="" entry="" hold=0 socket="" limit="" session="" chosen=""
  local verdict=no-user-session

  if [ -r "$record" ]; then
    read -r stamp entry < "$record"
    if [ -S "$entry" ]; then
      export WSL_INTEROP="$entry"
      return 0
    fi
    case "$entry" in
      no-user-session) hold=60 ;;
      unanswered) hold=10 ;;
    esac
    if [ -n "$stamp" ] && [[ "$stamp" != *[!0-9]* ]]; then
      # 10#: a stamp with a leading zero is not octal. A stamp from the future
      # (a clock moved back) is no reason to hold.
      local age=$((EPOCHSECONDS - 10#$stamp))
      [ "$age" -lt 0 ] || [ "$age" -ge "$hold" ] || return 0
    fi
  fi

  local deadline=$((EPOCHSECONDS + 3))
  for socket in $(ls -t "$socket_dir"/*_interop 2>/dev/null); do
    limit=$((deadline - EPOCHSECONDS))
    if [ "$limit" -le 0 ]; then
      verdict=unanswered
      break
    fi
    [ "$limit" -le 2 ] || limit=2
    if ! session=$(WSL_INTEROP="$socket" timeout -k 1 "$limit" "$powershell" \
        -NoProfile -NonInteractive -Command '(Get-Process -Id $PID).SessionId' \
        </dev/null 2>/dev/null); then
      verdict=unanswered
      continue
    fi
    session="${session%%$'\r'*}"
    if [ -z "$session" ] || [[ "$session" == *[!0-9]* ]]; then
      verdict=unanswered
    elif [ "$session" != 0 ]; then
      chosen="$socket"
      break
    fi
  done

  # A rename, so a shell starting beside this one reads a whole record or none.
  { printf '%s %s\n' "$EPOCHSECONDS" "${chosen:-$verdict}" > "$record.$$" &&
    mv -f "$record.$$" "$record"; } 2>/dev/null
  [ -z "$chosen" ] || export WSL_INTEROP="$chosen"
}
__wsl_interop_repoint
unset -f __wsl_interop_repoint
