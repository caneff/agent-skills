#!/usr/bin/env python3
"""Footgun guard (PreToolUse, Bash): refuse two command shapes that destroy or
hang, and say what to run instead. Exit 2 with the reason on stderr blocks;
every other path exits 0.

1. A bare `rg` (#1860). `rg <pattern>` with no path reads stdin when stdin is
   not a tty, and the harness's stdin is neither a tty nor /dev/null, so the
   call hangs until its timeout (a controller sat mid-merge about 6 hours).
   Refused when a command word `rg` has no path operand and nothing supplies
   its stdin (a pipe into it, `<`, `<<<`, a heredoc). `--files` and the
   version/help flags read no pattern and never stdin, so they pass.

2. A truncate-then-read `open()` (#1704). `open(p,'w').write(open(p).read())`
   empties p when the first `open` runs, before the read. Refused when a
   Python `open(P, <mode with w>)` is followed, in the same statement (a
   `with` header's statement includes its body), by a reading `open(P ...)`
   of the same literal argument. Read into a variable first, then write. A
   read of a differently spelled path, or after the statement ends, is not
   seen: this guard stops a drifting agent, not a determined one.

A failure of the guard itself is said out loud (a systemMessage, exit 0): a
guard that crashed quietly would read as a command with nothing wrong in it.
It does not block on its own fault, since neither shape is a loss that
justifies refusing every Bash call.
"""
import json
import os
import re
import sys

# ---- shell tokenizer: words and operators, quotes and comments understood ----

# Longest first, so `<<<` is not read as `<<` then `<`.
OPERATORS = ("<<<", "<<-", "&&", "||", "|&", ";;", "<<", ">>", ">&", "&>", "<&",
             "|", ";", "&", "(", ")", "<", ">")
SEPARATORS = {"&&", "||", "|&", "|", ";", ";;", "&", "(", ")", "\n"}
PIPES = {"|", "|&"}
STDIN_OPS = {"<", "<<", "<<-", "<<<", "<&"}
REDIRECTS = STDIN_OPS | {">", ">>", ">&", "&>"}


def tokenize(s):
    """[(kind, text)], kind 'w' (a word, quotes removed) or 'o' (an operator;
    a newline outside quotes is the operator '\\n')."""
    out, cur, n, i = [], None, len(s), 0

    def flush():
        nonlocal cur
        if cur is not None:
            out.append(("w", cur))
            cur = None

    while i < n:
        c = s[i]
        if c in " \t\r":
            flush()
        elif c == "\n":
            flush()
            out.append(("o", "\n"))
        elif c == "#" and cur is None:
            while i < n and s[i] != "\n":
                i += 1
            continue
        elif c == "\\":
            if i + 1 < n and s[i + 1] != "\n":
                cur = (cur or "") + s[i + 1]
            i += 2
            continue
        elif c == "'":
            j = s.find("'", i + 1)
            j = n if j < 0 else j
            cur = (cur or "") + s[i + 1:j]
            i = j + 1
            continue
        elif c == '"':
            j, buf = i + 1, ""
            while j < n and s[j] != '"':
                if s[j] == "\\" and j + 1 < n:
                    j += 1
                buf += s[j]
                j += 1
            cur = (cur or "") + buf
            i = j + 1
            continue
        elif c == "`":
            flush()
            out.append(("o", ";"))
        elif c == "$" and s[i + 1:i + 2] == "(":
            flush()
            out.append(("o", "("))
            i += 2
            continue
        else:
            op = next((o for o in OPERATORS if s.startswith(o, i)), None)
            if op:
                # `2>&1`: the digits are a file descriptor, not an operand.
                if cur is not None and cur.isdigit() and op[0] in "<>":
                    cur = None
                flush()
                out.append(("o", op))
                i += len(op)
                continue
            cur = (cur or "") + c
        i += 1
    flush()
    return out


def commands(tokens):
    """Yield (words, piped_in, stdin_supplied) per simple command."""
    words, piped, stdin, prev_pipe, skip = [], False, False, False, False

    def done():
        nonlocal words, piped, stdin, skip
        if words:
            yield (words, piped, stdin)
        words, piped, stdin, skip = [], False, False, False

    for kind, text in tokens:
        if kind == "o" and text in SEPARATORS:
            yield from done()
            prev_pipe = text in PIPES
            continue
        if not words and not stdin:
            piped = prev_pipe
        if kind == "o":
            if text in REDIRECTS:
                skip = True  # the next word is the redirect's target
                stdin = stdin or text in STDIN_OPS
            continue
        if skip:
            skip = False
            continue
        words.append(text)
    yield from done()


# ---- guard 1: bare rg ----

PREFIX = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "sudo",
          "time", "env", "nohup", "exec", "command"}
# rg flags that take a value as their own word (the short ones, and the long
# ones given without `=`).
SHORT_VALUE = set("efgtTmACBjEMrd")
LONG_VALUE = {"--regexp", "--file", "--glob", "--iglob", "--type", "--type-not",
              "--type-add", "--max-count", "--after-context", "--before-context",
              "--context", "--threads", "--replace", "--max-columns",
              "--max-depth", "--maxdepth", "--max-filesize", "--encoding",
              "--colors", "--sort", "--sortr", "--engine", "--ignore-file",
              "--pre", "--pre-glob", "--path-separator", "--context-separator",
              "--dfa-size-limit", "--regex-size-limit", "--field-match-separator",
              "--field-context-separator", "--hyperlink-format", "--generate"}
PATTERN_FLAGS = {"--regexp", "--file"}
NO_SEARCH = {"--files", "--type-list", "--help", "-h", "--version", "-V",
             "--pcre2-version", "--generate"}


def strip_prefix(words):
    while words and (words[0] in PREFIX or re.match(r"[A-Za-z_][A-Za-z0-9_]*=", words[0])):
        words = words[1:]
    return words


def rg_is_bare(args):
    """True when these rg arguments name no path to search."""
    positionals, has_pattern_flag, i = 0, False, 0
    while i < len(args):
        a = args[i]
        i += 1
        if a in NO_SEARCH:
            return False
        if a == "--":
            positionals += len(args) - i
            break
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            has_pattern_flag |= name in PATTERN_FLAGS
            if name in LONG_VALUE and "=" not in a:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for k, ch in enumerate(a[1:], 1):
                if ch in SHORT_VALUE:
                    has_pattern_flag |= ch in "ef"
                    if k == len(a) - 1:
                        i += 1  # the value is the next word
                    break  # else the rest of the cluster is the value
        else:
            positionals += 1
    return positionals <= (0 if has_pattern_flag else 1)


def bare_rg(scan):
    if not re.search(r"(^|[^A-Za-z0-9_.-])rg([^A-Za-z0-9_.-]|$)", scan):
        return False
    for words, piped, stdin in commands(tokenize(scan)):
        words = strip_prefix(words)
        if not words or os.path.basename(words[0]) != "rg":
            continue
        if piped or stdin:
            continue
        if rg_is_bare(words[1:]):
            return True
    return False


# ---- guard 2: truncate-then-read open() ----

WRITE_OPEN = re.compile(
    r"""\bopen\(\s*(?P<arg>[^,()]*(?:\([^()]*\)[^,()]*)*?)\s*,\s*(?:mode\s*=\s*)?['"](?P<mode>[^'"]*)['"]""")
MODE_LITERAL = re.compile(r"""['"]([rwaxbt+U]+)['"]""")


def norm(arg):
    return re.sub(r"""\s+|['"]""", "", arg)


def statement_tail(text, start):
    """Text from `start` to the end of its statement: a top-level `;` or a
    newline outside brackets. A header ending in `:` (a `with`) takes the
    lines indented deeper than the header's line."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        elif c == ";" and depth == 0:
            return text[start:i]
        elif c == "\n" and depth == 0:
            break
        i += 1
    head = text[start:i]
    if not head.rstrip().endswith(":"):
        return head
    line_start = text.rfind("\n", 0, start) + 1
    indent = len(text[line_start:]) - len(text[line_start:].lstrip(" \t"))
    body = [head]
    for line in text[i + 1:].split("\n"):
        if line.strip() and len(line) - len(line.lstrip(" \t")) <= indent:
            break
        body.append(line)
    return "\n".join(body)


def reads_after_truncate(command):
    if "open(" not in command:
        return None
    # `python3 -c "open(p,\"w\")"`: the shell's quoting layer is not python's.
    text = command.replace('\\"', '"').replace("\\'", "'")
    for m in WRITE_OPEN.finditer(text):
        if not re.search(r"[w]", m.group("mode")):
            continue
        arg = norm(m.group("arg"))
        if not arg:
            continue
        tail = statement_tail(text, m.end())
        for r in re.finditer(r"\bopen\(\s*(?P<arg>[^,()]*(?:\([^()]*\)[^,()]*)*?)\s*[,)]", tail):
            if norm(r.group("arg")) != arg:
                continue
            call_end = tail.find(")", r.start())
            call = tail[r.start():call_end + 1 if call_end >= 0 else None]
            mode = MODE_LITERAL.search(call)
            if mode and re.search(r"[wax]", mode.group(1)):
                continue
            return m.group("arg").strip()
    return None


# ---- heredocs: a body is data, not a command ----

HEREDOC = re.compile(r"""(^|[^<])<<-?\s*["'`]?([A-Za-z_][A-Za-z0-9_]*)""")


def strip_heredocs(command):
    out, delim = [], None
    for line in command.split("\n"):
        if delim is not None:
            if line.strip() == delim:
                delim = None
            continue
        out.append(line)
        m = HEREDOC.search(line)
        if m:
            delim = m.group(2)
    return "\n".join(out)


# ---- main ----

def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return 0
        command = (data.get("tool_input") or {}).get("command") or ""
        if not isinstance(command, str):
            raise TypeError("tool_input.command is not a string")
        # The heredoc body of `python3 - <<EOF` is the code guard 2 must read.
        path = reads_after_truncate(command)
        if path is not None:
            print(f"BLOCKED: '{command[:200]}' opens {path} for writing and reads it "
                  "in the same statement. The write-mode open truncates the file "
                  "before the read runs, so the file ends up empty. Read into a "
                  "variable first, then write: `s = open(p).read()` then "
                  "`open(p, 'w').write(f(s))`.", file=sys.stderr)
            return 2
        if bare_rg(strip_heredocs(command)):
            print(f"BLOCKED: '{command[:200]}' runs rg with no path. The harness's "
                  "stdin is neither a tty nor /dev/null, so rg reads stdin and the "
                  "call hangs until its timeout. Pass a path (`rg <pattern> .`) or "
                  "use `git grep <pattern>`.", file=sys.stderr)
            return 2
        return 0
    except Exception as e:  # noqa: BLE001 — the guard's own fault is reported, never silent
        print(json.dumps({"systemMessage": f"block-footguns.py: guard did not run: {type(e).__name__}: {e}"}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
