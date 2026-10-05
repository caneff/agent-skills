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
# it. Byte-wise (LC_ALL=C): every character it acts on is ASCII.
# A `#` opens a comment only at the start of a word: after an unquoted,
# unescaped blank or separator. `a\ #x` is one word, and its `#` is text.
# One awk pass per view, linear in the command: a bash loop that appended to
# two strings per character took 2.6 s on 44 KB and 5.9 s on 66 KB, past a
# hook's 5 s timeout, and a guard that times out lets the command through
# (#1423). Both are `$(...)` captures, so trailing newlines are dropped.
quote_views() {
  BARE=$(printf '%s' "$1" | LC_ALL=C awk -v view=bare "$QUOTE_VIEW_AWK")
  EXPANDS=$(printf '%s' "$1" | LC_ALL=C awk -v view=exp "$QUOTE_VIEW_AWK")
}

# The lexer, state carried across lines: q is the open quote, word_start says
# the next unquoted character begins a word. Per line it walks the bytes;
# `eat` is set when a backslash took the line's newline as its escaped char.
QUOTE_VIEW_AWK='
function put(b, e) { printf "%s", (view == "bare" ? b : e) }
BEGIN { q = ""; word_start = 1 }
{
  n = length($0); eat = 0
  for (i = 1; i <= n; i++) {
    c = substr($0, i, 1)
    if (q == "" && c == "#" && word_start) break
    word_start = 0
    if (q == "" && c ~ /[ \t\v\f\r;&|(]/) word_start = 1
    if (q == "\047") { if (c == "\047") q = ""; continue }
    if (q == "\"") {
      if (c == "\\") {
        d = substr($0, i + 1, 1); put("", c d)
        if (i == n) eat = 1
        i++
      } else if (c == "\"") q = ""
      else put("", c)
      continue
    }
    if (c == "\047" || c == "\"") q = c
    else if (c == "\\") {
      d = substr($0, i + 1, 1); put(c d, c d)
      if (i == n) eat = 1
      i++
    } else put(c, c)
  }
  if (eat) { put("\n", "\n"); next }
  if (q == "") { put("\n", "\n"); word_start = 1 }
  else if (q == "\"") put("", "\n")
}'
