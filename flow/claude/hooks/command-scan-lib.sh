#!/bin/bash
# Command-text scanning shared by the Bash hooks that must tell a command
# being run from text that merely mentions it: block-dangerous-git.sh (a
# guard) and the teaching hooks (teach-*.sh). Sourced, never run.

# A heredoc body is data being written to a file, not a command being run.
# Scanning it for a command produces false positives: writing a doc that
# mentions a blocked git verb is harmless, yet a raw grep would block it.
# Strip heredoc bodies, keeping the opener line, which may carry the real
# command. A caller scans the result and still quotes the original command in
# any message.
strip_heredocs() {
  local line delim="" indoc=0 trimmed
  local re='<<-?[[:space:]]*["'"'"'`]?([A-Za-z_][A-Za-z0-9_]*)'
  while IFS= read -r line; do
    if [ "$indoc" -eq 1 ]; then
      trimmed="${line#"${line%%[![:space:]]*}"}"
      if [ "$line" = "$delim" ] || [ "$trimmed" = "$delim" ]; then indoc=0; fi
      continue
    fi
    if [[ "$line" =~ $re ]]; then delim="${BASH_REMATCH[1]}"; indoc=1; fi
    printf '%s\n' "$line"
  done
}

# Two views of $1 from one pass that tracks quoting: BARE drops every quoted
# character (what the shell runs as words); EXPANDS drops only single-quoted
# ones, since `$(...)` and backticks still run inside double quotes. Both drop
# an unquoted `#` comment up to its newline: nothing in it runs, and an
# apostrophe in one would otherwise open a quote that hides every line after
# it. Byte-wise (LC_ALL=C): every character it acts on is ASCII, and in a
# UTF-8 locale `${s:i:1}` walks the string from the start, which made a 20 KB
# command take three seconds.
quote_views() {
  local LC_ALL=C
  local s=$1 i c q="" bare="" exp=""
  for ((i = 0; i < ${#s}; i++)); do
    c=${s:i:1}
    if [ -z "$q" ] && [ "$c" = '#' ] && { [ "$i" = 0 ] || [[ "${s:i-1:1}" == [[:space:]\;\&\|\(] ]]; }; then
      while [ "$i" -lt "${#s}" ] && [ "${s:i:1}" != $'\n' ]; do i=$((i + 1)); done
      bare+=$'\n'; exp+=$'\n'
      continue
    fi
    case "$q" in
      "'") [ "$c" = "'" ] && q="" ;;
      '"')
        if [ "$c" = '\' ]; then exp+=$c${s:i+1:1}; i=$((i + 1))
        elif [ "$c" = '"' ]; then q=""
        else exp+=$c; fi ;;
      *)
        case "$c" in
          "'" | '"') q=$c ;;
          '\') bare+=$c${s:i+1:1}; exp+=$c${s:i+1:1}; i=$((i + 1)) ;;
          *) bare+=$c; exp+=$c ;;
        esac ;;
    esac
  done
  BARE=$bare EXPANDS=$exp
}
