# Sourced, never run: moves WSL_INTEROP off a dead socket (#1625). A process tree
# outliving its Windows session keeps a WSL_INTEROP whose socket is gone, and
# every Windows call from it then lands in session 0 with no error: nothing
# appears on the desktop and the clipboard reads empty.
#
# Two carriers: `env.BASH_ENV` in claude/settings.json reaches a Claude Code Bash
# tool call and `!` command, which skip ~/.bashrc's interactive part, and the
# line flow/install.sh appends to ~/.bashrc reaches a new herdr pane shell.
# flow/install-check.sh names either one missing.
#
# BASH_ENV runs this before every non-interactive bash, including `bash -eu`
# scripts and ones whose stdout or stdin is another program's. So it prints
# nothing, survives -e and -u, keeps stdin from its probes, leaves no name behind.
#
# What each case costs:
# - WSL_INTEROP is a socket: one file test, no Windows process. A live socket
#   reaching session 0 stays, since telling that takes a Windows process.
# - Dead or unset (both land in session 0, measured 2026-11-03), a socket already
#   found this boot: one file read, no Windows process.
# - Otherwise it asks PowerShell for the session behind each socket under
#   /run/WSL, newest first, and takes the first non-zero one: session 0 is
#   Windows' services session and every other is a user's. A liveness test
#   cannot choose here: of seven live sockets, three reached session 0.
#   Each probe gets 3 s (0.25 s measured) and all of them 8 s, plus 1 s to kill a
#   probe ignoring its timeout, so the most a shell waits is 9 s.
# - Nothing found: the variable stays as it was and the command runs unchanged.
#   The record stops every shell repeating that wait for the next 60 s.
#
# The record lives in the runtime tmpfs because a socket's path means nothing
# after a WSL restart. The WSL_INTEROP_* overrides are the test's seams.
__wsl_interop_repoint() {
  [ -S "${WSL_INTEROP:-}" ] && return 0
  local sockets="${WSL_INTEROP_SOCKET_DIR:-/run/WSL}"
  [ -d "$sockets" ] || return 0
  local ps="${WSL_INTEROP_POWERSHELL:-/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe}"
  local record="${WSL_INTEROP_CACHE_DIR:-${XDG_RUNTIME_DIR:-/run/user/$UID}}/wsl-interop-repoint"
  local stamp="" found="" socket="" limit="" session="" chosen=""

  if [ -r "$record" ]; then
    read -r stamp found < "$record" 2>/dev/null
    if [ -n "$found" ] && [ -S "$found" ]; then
      export WSL_INTEROP="$found"
      return 0
    fi
    if [ -z "$found" ] && [[ "$stamp" =~ ^[0-9]+$ ]] && [ $((EPOCHSECONDS - stamp)) -lt 60 ]; then
      return 0
    fi
  fi

  local deadline=$((EPOCHSECONDS + 8))
  for socket in $(ls -t "$sockets"/*_interop 2>/dev/null); do
    limit=$((deadline - EPOCHSECONDS))
    [ "$limit" -gt 0 ] || break
    [ "$limit" -le 3 ] || limit=3
    session=$(WSL_INTEROP="$socket" timeout -k 1 "$limit" "$ps" -NoProfile -NonInteractive \
      -Command '(Get-Process -Id $PID).SessionId' </dev/null 2>/dev/null) || continue
    session="${session%%$'\r'*}"
    if [[ "$session" =~ ^[0-9]+$ ]] && [ "$session" != 0 ]; then
      chosen="$socket"
      break
    fi
  done

  # A rename, so a shell starting beside this one reads a whole record or none.
  { printf '%s %s\n' "$EPOCHSECONDS" "$chosen" > "$record.$$" && mv -f "$record.$$" "$record"; } 2>/dev/null
  [ -z "$chosen" ] || export WSL_INTEROP="$chosen"
}
__wsl_interop_repoint || :
unset -f __wsl_interop_repoint
