#!/usr/bin/env bash
# Fixture test for herdr-toast-install. Every run gets its own $HOME and a
# `powershell.exe` stub first on PATH that records its arguments, so the real
# registry cannot be reached and every case asserts whether the stub was called.
# A run that reaches the real registry is the failure this test exists to stop.
# The stub is a PATH name: it covers the installer's bare `powershell.exe` call
# only, so an absolute /mnt/c path added to the installer would bypass it.
# Run from flow/bin/.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fails=0
fail() { echo "FAIL: $*"; fails=1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
names="notify-send run-hidden.vbs herdr-focus.vbs herdr-focus-pick.ps1 herdr-focus-latest"

mkdir -p "$tmp/stub"
cat > "$tmp/stub/powershell.exe" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$STUB_LOG"
STUB
cat > "$tmp/stub/wslpath" <<'STUB'
#!/usr/bin/env bash
printf '\\\\wsl.localhost\\Ubuntu-24.04%s\n' "$(printf '%s' "$2" | tr / '\\')"
STUB
chmod +x "$tmp/stub/"*

# run_install <case> <installer dir> [extra env...]: fresh HOME, stub log; sets rc.
run_install() {
  c=$1; dir=$2; shift 2
  export STUB_LOG="$tmp/$c.log"; : >"$STUB_LOG"
  mkdir -p "$tmp/$c/.local/bin"
  env HOME="$tmp/$c" PATH="$tmp/stub:$PATH" "$@" bash "$dir/herdr-toast-install" >"$tmp/$c.out" 2>&1
  rc=$?
}
mkfix() { mkdir -p "$1"; cp "$here/herdr-toast-install" "$1/"; for n in $names; do echo x >"$1/$n"; done; }

# 1. happy path: links made, registry written once, pointing at the fixture and never .local\bin
mkfix "$tmp/ok/flow/bin"
mkdir -p "$tmp/ok/.local/bin"; for n in $names; do echo old >"$tmp/ok/.local/bin/$n"; done
echo keep >"$tmp/ok/.local/bin/notify-send.bak-x"
run_install ok "$tmp/ok/flow/bin" HERDR_TOAST_ALLOW_TMP=1
[ $rc = 0 ] || fail "happy path exited $rc: $(cat "$tmp/ok.out")"
for n in $names; do
  [ "$(readlink "$tmp/ok/.local/bin/$n")" = "$tmp/ok/flow/bin/$n" ] || fail "$n is not a symlink to flow/bin"
  [ "$(cat "$tmp/ok/.local/bin/$n.pre-flow")" = old ] || fail "$n's real file was not kept as .pre-flow"
done
[ "$(cat "$tmp/ok/.local/bin/notify-send.bak-x")" = keep ] || fail ".bak file touched"
[ "$(wc -l <"$tmp/ok.log")" = 1 ] || fail "registry stub not called exactly once ($(wc -l <"$tmp/ok.log") calls)"
grep -qF "$(printf '%s' "$tmp/ok/flow/bin" | tr / '\\')\\herdr-focus.vbs" "$tmp/ok.log" || fail "registry value does not name the fixture's herdr-focus.vbs"
grep -qF '.local\bin' "$tmp/ok.log" && fail "registry value names a .local path"

# 2. refuses under /tmp without the override: no links, no registry call
mkfix "$tmp/t/flow/bin"
run_install t "$tmp/t/flow/bin"
[ $rc != 0 ] || fail "ran from /tmp without the override"
[ -z "$(ls "$tmp/t/.local/bin")" ] || fail "linked something after refusing /tmp"
[ ! -s "$tmp/t.log" ] || fail "registry stub called after refusing /tmp"

# 3. refuses from a linked worktree even with the /tmp override
git init -q "$tmp/repo" && git -C "$tmp/repo" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
git -C "$tmp/repo" worktree add -q "$tmp/wt" -b wt
mkfix "$tmp/wt/flow/bin"
run_install w "$tmp/wt/flow/bin" HERDR_TOAST_ALLOW_TMP=1
[ $rc != 0 ] || fail "ran from a linked worktree"
grep -q worktree "$tmp/w.out" || fail "worktree refusal did not say why: $(cat "$tmp/w.out")"
[ -z "$(ls "$tmp/w/.local/bin")" ] || fail "linked something after refusing a worktree"
[ ! -s "$tmp/w.log" ] || fail "registry stub called after refusing a worktree"

# 4. a real directory at a destination is refused before anything is touched
mkfix "$tmp/d/flow/bin"; mkdir -p "$tmp/d/.local/bin/herdr-focus.vbs"
run_install d "$tmp/d/flow/bin" HERDR_TOAST_ALLOW_TMP=1
[ $rc != 0 ] || fail "ran over a real directory"
[ ! -e "$tmp/d/.local/bin/notify-send" ] || fail "linked before refusing the directory"
[ ! -s "$tmp/d.log" ] || fail "registry stub called after refusing a directory"

# 5. every Windows-read file names no ~/.local/bin UNC path (Windows cannot follow the link)
for f in notify-send herdr-focus.vbs herdr-focus-pick.ps1 run-hidden.vbs; do
  [ -f "$here/$f" ] || { fail "$f missing from flow/bin"; continue; }
  grep -q 'wsl.localhost.*\.local' "$here/$f" && fail "$f names a UNC path into .local"
done

[ $fails = 0 ] && echo ok
exit $fails
