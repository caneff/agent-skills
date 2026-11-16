#!/bin/bash
# Footgun guard shim (PreToolUse, Bash): runs block-footguns.py beside it.
# Registered as `bash <path>` on purpose. Registered as `python3 <path>`, a
# missing script makes python3 exit 2, which blocks every Bash call; here a
# missing script or python3 is said out loud and the call goes through. Being a
# .sh also puts the registration under install-check.sh.
py="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/block-footguns.py"
if [ ! -r "$py" ] || ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' '{"systemMessage": "block-footguns.sh: guard did not run: block-footguns.py is missing beside it, or python3 is not on PATH."}'
  exit 0
fi
exec python3 -I "$py"
