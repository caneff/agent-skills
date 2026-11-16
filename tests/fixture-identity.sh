# Sourced by every suite that writes a commit identity into a fixture repo.
# fixture_identity <repo> <root>: set user.email/user.name in <repo> only when
# <repo>'s toplevel sits under <root> (the caller's own mktemp dir); else
# print a FAIL line and return 1, writing nothing. A bare `git config` after a
# failed `cd` wrote the real checkout's config (#1144), so the target is named
# and checked. The refusal path is tested by tests/fixture-identity.test.sh.
fixture_identity() {
  # An empty or missing root resolves to "", and "/*" would admit any repo.
  local root
  root=$([ -n "$2" ] && cd "$2" && pwd -P) && [ -n "$root" ] ||
    { echo "FAIL: fixture root '$2' does not resolve to a directory" >&2; return 1; }
  case "$(git -C "$1" rev-parse --show-toplevel 2>/dev/null)" in
    "$root"/*) ;;
    *) echo "FAIL: fixture repo $1 is not under $2" >&2; return 1 ;;
  esac
  git -C "$1" config user.email t@example.invalid
  git -C "$1" config user.name t
}

# fixture_env: export the same identity as GIT_AUTHOR_*/GIT_COMMITTER_*, for a
# suite that commits through the environment. Run it where the exports may
# stay (a subshell, or a suite whose whole shell is a fixture); it writes no
# config, so it needs no repo to check.
fixture_env() {
  export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid
  export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
}
