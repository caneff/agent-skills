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
# Neither a here-string (`<<<`) nor a shift inside `$(( ))` opens a heredoc:
# taking one for an opener would drop every line after it, a command included.
strip_heredocs() {
  local line delim="" indoc=0 trimmed rest before
  local re='(^|[^<])<<-?[[:space:]]*["'"'"'`]?([A-Za-z_][A-Za-z0-9_]*)'
  while IFS= read -r line; do
    if [ "$indoc" -eq 1 ]; then
      trimmed="${line#"${line%%[![:space:]]*}"}"
      if [ "$line" = "$delim" ] || [ "$trimmed" = "$delim" ]; then indoc=0; fi
      continue
    fi
    rest=$line
    while [[ "$rest" =~ $re ]]; do
      before=${rest%%"${BASH_REMATCH[0]}"*}${BASH_REMATCH[1]}
      rest=${rest#*"${BASH_REMATCH[0]}"}
      # An arithmetic `((` still open before the `<<` makes it a shift.
      [[ "$before" == *'(('* && "${before##*((}" != *'))'* ]] && continue
      delim="${BASH_REMATCH[2]}"; indoc=1; break
    done
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
# A `#` opens a comment only at the start of a word: after an unquoted,
# unescaped blank or separator. `a\ #x` is one word, and its `#` is text.
quote_views() {
  local LC_ALL=C
  local s=$1 i c q="" bare="" exp="" word_start=1
  for ((i = 0; i < ${#s}; i++)); do
    c=${s:i:1}
    if [ -z "$q" ] && [ "$c" = '#' ] && [ "$word_start" = 1 ]; then
      while [ "$i" -lt "${#s}" ] && [ "${s:i:1}" != $'\n' ]; do i=$((i + 1)); done
      bare+=$'\n'; exp+=$'\n'
      continue
    fi
    word_start=0
    [ -z "$q" ] && [[ "$c" == [[:space:]\;\&\|\(] ]] && word_start=1
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
