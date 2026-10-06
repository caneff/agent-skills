#!/usr/bin/env bash
# Selfcheck for lib.sh: platform detection and the /proc/net/route gateway
# parse, both driven on canned input so the test needs no real OS signals.
# Run: bash marimo-pair/scripts/lib.test.sh
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$here/lib.sh"
fails=0

# run <name> <actual> <expected>
run() {
  local name=$1 actual=$2 expected=$3
  if [[ "$actual" == "$expected" ]]; then
    echo "PASS: $name"
  else
    echo "FAIL: $name — want '$expected', got '$actual'"
    fails=1
  fi
}

# --- detect_platform ---

got=$(OSTYPE=msys32 WSL_DISTRO_NAME= bash -c "source '$here/lib.sh'; detect_platform")
run "OSTYPE=msys* reports windows" "$got" "windows"

got=$(OSTYPE=cygwin WSL_DISTRO_NAME= bash -c "source '$here/lib.sh'; detect_platform")
run "OSTYPE=cygwin reports windows" "$got" "windows"

got=$(unset OSTYPE; WSL_DISTRO_NAME=Ubuntu-24.04 bash -c "source '$here/lib.sh'; detect_platform")
run "WSL_DISTRO_NAME set reports wsl" "$got" "wsl"

got=$(unset OSTYPE WSL_DISTRO_NAME; bash -c "
  source '$here/lib.sh'
  grep() { return 0; } # simulate 'microsoft' present in /proc/version
  detect_platform
")
run "microsoft in /proc/version reports wsl" "$got" "wsl"

got=$(unset OSTYPE WSL_DISTRO_NAME; bash -c "
  source '$here/lib.sh'
  grep() { return 1; } # simulate no WSL signal at all
  detect_platform
")
run "no signals reports posix" "$got" "posix"

# --- parse_proc_net_route ---

route_file=$(mktemp)
trap 'rm -f "$route_file"' EXIT

# Real /proc/net/route shape: header line, then one row per route. Gateway
# 0102A8C0 little-endian hex == 192.168.2.1.
cat >"$route_file" <<'EOF'
Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask		MTU	Window	IRTT
eth0	00000000	0102A8C0	0003	0	0	0	00000000	0	0	0
eth0	0002A8C0	00000000	0001	0	0	0	00FFFFFF	0	0	0
EOF

got=$(parse_proc_net_route "$route_file")
run "parses default route gateway from canned route table" "$got" "192.168.2.1"

no_default_file=$(mktemp)
cat >"$no_default_file" <<'EOF'
Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask		MTU	Window	IRTT
eth0	0002A8C0	00000000	0001	0	0	0	00FFFFFF	0	0	0
EOF
got=$(parse_proc_net_route "$no_default_file")
run "no default route parses to empty" "$got" ""
rm -f "$no_default_file"

got=$(parse_proc_net_route "/nonexistent/route/file")
run "missing route file parses to empty" "$got" ""

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
