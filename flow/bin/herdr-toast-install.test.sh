#!/usr/bin/env bash
# Fixture test for herdr-toast-install. Every run gets its own $HOME and a
# `reg.exe` stub first on PATH that records its arguments, so the real
# registry cannot be reached and every case asserts whether the stub was called.
# A run that reaches the real registry is the failure this test exists to stop.
# The stub is a PATH name: it covers the installer's bare `reg.exe` call
# only, so an absolute /mnt/c path added to the installer would bypass it.
# Run from flow/bin/.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fails=0
fail() { echo "FAIL: $*"; fails=1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
names="notify-send run-hidden.vbs herdr-focus.vbs herdr-focus-pick.ps1 herdr-focus-latest"

mkdir -p "$tmp/stub"
# reg.exe records one `[arg]` line per argument, so a quoting change shows up
# exactly; STUB_RC makes it fail. powershell.exe is stubbed too, so a change that
# routes the write back through it is still caught by the exactly-once count.
for x in reg.exe powershell.exe; do
  cat > "$tmp/stub/$x" <<'STUB'
#!/usr/bin/env bash
printf '[%s]\n' "$@" >>"$STUB_LOG"
exit "${STUB_RC:-0}"
STUB
done
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
check_reg() { # <case> <fixture bin dir>: the whole registry call, one write, exact command string
  unc=$(printf '%s' "$2" | tr / '\\')
  want=$(printf '[add]\n[HKCU\\Software\\Classes\\herdrfocus\\shell\\open\\command]\n[/ve]\n[/d]\n[wscript.exe //B //Nologo "\\\\wsl.localhost\\Ubuntu-24.04%s\\herdr-focus.vbs" "%%1"]\n[/f]\n' "$unc")
  [ "$(cat "$tmp/$1.log")" = "${want%$'\n'}" ] || fail "$1: registry call is not exactly the quoted command: $(cat "$tmp/$1.log")"
}
check_reg ok "$tmp/ok/flow/bin"

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

# 5. a registry failure leaves ~/.local/bin untouched: real files stay real, no .pre-flow
mkfix "$tmp/f/flow/bin"; mkdir -p "$tmp/f/.local/bin"; for n in $names; do echo old >"$tmp/f/.local/bin/$n"; done
run_install f "$tmp/f/flow/bin" HERDR_TOAST_ALLOW_TMP=1 STUB_RC=1
[ $rc != 0 ] || fail "exited 0 after the registry write failed"
for n in $names; do
  [ ! -L "$tmp/f/.local/bin/$n" ] && [ "$(cat "$tmp/f/.local/bin/$n")" = old ] || fail "$n was replaced although the registry write failed"
  [ ! -e "$tmp/f/.local/bin/$n.pre-flow" ] || fail "$n.pre-flow made although the registry write failed"
done

# 6. a fixture directory with a space keeps the quoted form intact
mkfix "$tmp/sp ace/flow/bin"
run_install s "$tmp/sp ace/flow/bin" HERDR_TOAST_ALLOW_TMP=1
[ $rc = 0 ] || fail "space-in-path run exited $rc: $(cat "$tmp/s.out")"
check_reg s "$tmp/sp ace/flow/bin"

# 7. every Windows-read file names no ~/.local/bin UNC path (Windows cannot follow the link)
for f in notify-send herdr-focus.vbs herdr-focus-pick.ps1 run-hidden.vbs; do
  [ -f "$here/$f" ] || { fail "$f missing from flow/bin"; continue; }
  grep -q 'wsl.localhost.*\.local' "$here/$f" && fail "$f names a UNC path into .local"
done

[ $fails = 0 ] && echo ok
exit $fails
