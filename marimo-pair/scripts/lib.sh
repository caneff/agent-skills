# Shared helpers for marimo-pair's scripts. Source this from a script's own
# directory: `source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"`.
# Not executable on its own; no shebang, no `set -euo pipefail` (the sourcing
# script owns those).

# Exit 1 with a message on stderr if any of the named tools is not on PATH.
# Reports the caller's own script name ($0), matching each script's prior
# inline check.
require_tools() {
  local missing="" tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || missing="${missing:+$missing, }$tool"
  done
  if [[ -n "$missing" ]]; then
    echo "$(basename "$0") needs ${missing} on PATH." >&2
    exit 1
  fi
}

# Echoes one of: windows, wsl, posix.
detect_platform() {
  if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
    echo windows
  elif [[ -n "${WSL_DISTRO_NAME:-}" ]] || grep -qi microsoft /proc/version 2>/dev/null; then
    echo wsl
  else
    echo posix
  fi
}

# Parse the default gateway out of a /proc/net/route-style file: the row
# whose destination and mask are both zero, gateway field as little-endian
# hex. Echoes the dotted-quad address, or nothing if there is no default
# route or the file cannot be read.
parse_proc_net_route() {
  local file=$1 hex
  [[ -r "$file" ]] || return 0
  hex=$(awk '$2 == "00000000" && $8 == "00000000" { print $3; exit }' "$file" 2>/dev/null) || hex=""
  [[ "$hex" =~ ^[0-9A-Fa-f]{8}$ ]] || return 0
  printf '%d.%d.%d.%d' "0x${hex:6:2}" "0x${hex:4:2}" "0x${hex:2:2}" "0x${hex:0:2}"
}

# The default gateway, which under WSL NAT is the Windows host. Tries `ip`
# first, then falls back to reading the kernel route table directly (no
# iproute2). Echoes the address, or nothing if it cannot be determined.
find_gateway() {
  local route_file="${1:-/proc/net/route}" gateway=""
  if command -v ip >/dev/null 2>&1; then
    # `|| gateway=""` keeps `set -e` from killing the caller before the
    # fallback runs.
    gateway=$(ip route show default 2>/dev/null | awk 'NR == 1 { print $3 }') || gateway=""
  fi
  if [[ -z "$gateway" ]]; then
    gateway=$(parse_proc_net_route "$route_file")
  fi
  printf '%s' "$gateway"
}
