#!/usr/bin/env python3
"""Footgun guard (PreToolUse, Bash): refuse four command shapes that destroy,
hang or get denied, and say what to run instead. Exit 2 with the reason on
stderr blocks; every other path exits 0.

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

3. A backtick command substitution (#1923). Claude Code's built-in safety check
   cannot parse the legacy form, so it refuses the whole call as a possible
   dangerous `rm` even when nothing is removed (`$((`date +%s`-started))`).
   Refused when a backtick pair bash would run sits in a command, in double
   quotes, in a `$(...)` body, in a `bash -c` script or in an unquoted-delimiter
   heredoc body, with the `$(...)` rewrite in the message. A backtick in single
   quotes, a quoted-delimiter heredoc, a comment or after a backslash is text
   and passes.

4. A command that replaces the `~/.claude/settings.json` symlink (#2047). That
   path links into `flow/claude/settings.json`; `mv`, `install`, `ln`,
   `cp --remove-destination` and `sed -i` / `perl -i` (without sed's
   `--follow-symlinks`) put a plain file where the link was and detach the
   live config from the repo. Refused when the destination operand is that path,
   written literally, as `~/` or as `$HOME/`. Plain `cp`, a redirect, and any
   edit of the real file under `flow/claude/` write through the link and pass.
   A relative spelling after a `cd` is not seen.

A failure of the guard itself is said out loud (a systemMessage, exit 0): a
guard that crashed quietly would read as a command with nothing wrong in it.
It does not block on its own fault, since none of these shapes is a loss that
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


def close_paren(s, start):
    """The index of the `)` closing a `$(` whose body starts at `start`, or
    len(s) when it never closes. A paren in quotes or after a backslash is
    text, so `$(printf '(')` closes at its own `)`."""
    depth, i, n = 1, start, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                return n
            i = j + 1
            continue
        if c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            if j >= n:
                return n
            i = j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def tokenize(s, nested, ticks=None):
    """[(kind, text)], kind 'w' (a word, quotes removed) or 'o' (an operator;
    a newline outside quotes is the operator '\\n'). A `$(...)` or backtick
    body is part of the word it sits in (`rg x $(git ls-files)` names a path)
    and is appended to `nested` as text to scan as commands of its own; an
    backtick body, unquoted or inside double quotes, is also appended to
    `ticks`, when given."""
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
                elif s[j] == "$" and s[j + 1:j + 2] == "(":
                    # A `$(...)` body is a script of its own, where quotes count
                    # again: `"$(printf 'a `x` b')"` holds no substitution.
                    end = close_paren(s, j + 2)
                    if end >= n:
                        # Never closed: read on as plain double-quoted text,
                        # so the string still ends at its own `"`.
                        buf += s[j]
                        j += 1
                        continue
                    nested.append(s[j + 2:end])
                    buf += "$x"
                    j = end + 1
                    continue
                elif s[j] == "`" and ticks is not None:
                    end = s.find("`", j + 1)
                    end = n if end < 0 else end
                    ticks.append(s[j + 1:end])
                    buf += s[j:end + 1]
                    j = end + 1
                    continue
                buf += s[j]
                j += 1
            cur = (cur or "") + buf
            i = j + 1
            continue
        elif c == "`" or (c == "$" and s[i + 1:i + 2] == "("):
            start = i + (1 if c == "`" else 2)
            if c == "`":
                end = s.find("`", start)
                end = n if end < 0 else end
            else:
                end = close_paren(s, start)
            nested.append(s[start:end])
            if c == "`" and ticks is not None:
                ticks.append(s[start:end])
            cur = (cur or "") + "$x"
            i = end + 1
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
              "--field-context-separator", "--hyperlink-format"}
PATTERN_FLAGS = {"--regexp", "--file"}
NO_SEARCH = {"--files", "--type-list", "--help", "-h", "--version", "-V",
             "--pcre2-version", "--generate"}


# Wrappers that run the next command with their own options before it.
WRAPPERS = {"timeout", "nice", "stdbuf", "ionice"}
WRAPPER_ARG = re.compile(r"-.*|\d+[smhd]?$")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}


def strip_prefix(words):
    while words:
        w = words[0]
        if w in PREFIX or re.match(r"[A-Za-z_][A-Za-z0-9_]*=", w):
            words = words[1:]
        elif os.path.basename(w) in WRAPPERS:
            words = words[1:]
            while words and WRAPPER_ARG.match(words[0]):
                words = words[1:]
        else:
            break
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


def scan_commands(scan, depth=0, ticks=None):
    """Every (words, piped, stdin) in `scan`, including a `$(...)` body and the
    script of a `bash -c`, which run as commands too."""
    nested = []
    for cmd in commands(tokenize(scan, nested, ticks)):
        yield cmd
        words = strip_prefix(cmd[0])
        if depth < 5 and words and os.path.basename(words[0]) in SHELLS and "-c" in words[1:-1]:
            nested.append(words[words.index("-c", 1) + 1])
    if depth < 5:
        for body in nested:
            yield from scan_commands(body, depth + 1, ticks)


def bare_rg(scan):
    if not re.search(r"(^|[^A-Za-z0-9_.-])rg([^A-Za-z0-9_.-]|$)", scan):
        return False
    for words, piped, stdin in scan_commands(scan):
        words = strip_prefix(words)
        if not words or os.path.basename(words[0]) != "rg":
            continue
        if piped or stdin:
            continue
        if rg_is_bare(words[1:]):
            return True
    return False


def backtick_bodies(scan):
    """The text between each unquoted backtick pair in `scan`."""
    ticks = []
    for _ in scan_commands(scan, ticks=ticks):
        pass
    return ticks


def runs_python(scan):
    """True when some command in `scan` is a Python interpreter (`python3 -`,
    `uv run python`): only then is text shaped like `open(p,'w')` code. A
    commit message or an issue body that quotes the shape runs nothing."""
    for words, _, _ in scan_commands(scan):
        words = strip_prefix(words)
        if any(re.fullmatch(r"python[0-9.]*", os.path.basename(w)) for w in words[:3]):
            return True
    return False


# ---- guard 2: truncate-then-read open() ----

OPEN_ARG = r"(?P<arg>[^,()]*(?:\([^()]*\)[^,()]*)*?)"
OPEN_CALL = re.compile(r"\bopen\(\s*" + OPEN_ARG + r"\s*[,)]")
WRITE_OPEN = re.compile(
    r"""\bopen\(\s*""" + OPEN_ARG + r"""\s*,\s*(?:mode\s*=\s*)?['"](?P<mode>[^'"]*)['"]""")
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
        if "w" not in m.group("mode"):
            continue
        arg = norm(m.group("arg"))
        if not arg:
            continue
        tail = statement_tail(text, m.end())
        for r in OPEN_CALL.finditer(tail):
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

HEREDOC = re.compile(r"""(^|[^<])<<-?\s*(["'`]?)([A-Za-z_][A-Za-z0-9_]*)""")


def strip_heredocs(command, expanded=None):
    """`command` without its heredoc bodies. A body whose delimiter is not
    quoted is expanded by bash, so when `expanded` is a list its lines are
    appended to it."""
    out, delim, quoted = [], None, True
    for line in command.split("\n"):
        if delim is not None:
            if line.strip() == delim:
                delim = None
            elif not quoted and expanded is not None:
                expanded.append(line)
            continue
        out.append(line)
        for m in HEREDOC.finditer(line):
            # An arithmetic `((` still open before the `<<` makes it a shift.
            before = line[:m.start()] + m.group(1)
            if "((" in before and "))" not in before.rsplit("((", 1)[1]:
                continue
            delim, quoted = m.group(3), bool(m.group(2))
            break
    return "\n".join(out)


# ---- guard 4: replacing the settings.json symlink ----

HOME_FORMS = ("~/", "$HOME/", "${HOME}/")


def is_settings_link(word):
    """True when `word` spells ~/.claude/settings.json (text only: realpath
    would resolve the link, and the real file is the allowed target)."""
    home = os.path.expanduser("~")
    for form in HOME_FORMS:
        if word.startswith(form):
            word = home + "/" + word[len(form):]
            break
    return os.path.normpath(word) == os.path.join(home, ".claude", "settings.json")


def in_place_flag(arg, value_flags):
    """True when a short-option cluster or `--in-place` asks for in-place edit."""
    if arg.startswith("--"):
        return arg.split("=", 1)[0] == "--in-place"
    if not arg.startswith("-") or len(arg) < 2:
        return False
    for ch in arg[1:]:
        if ch == "i":
            return True
        if ch in value_flags:
            return False
    return False


def destinations(args):
    """The paths a mv/install/ln/cp writes: the last operand, or each source's
    name inside the `-t DIR` directory."""
    ops, target, i = [], None, 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            ops += args[i:]
            break
        if a in ("-t", "--target-directory"):
            target = args[i] if i < len(args) else None
            i += 1
        elif a.startswith("--target-directory="):
            target = a.split("=", 1)[1]
        elif a.startswith("-t") and not a.startswith("--") and len(a) > 2:
            target = a[2:]
        elif a.startswith("-") and len(a) > 1:
            continue
        else:
            ops.append(a)
    if target is not None:
        return [target.rstrip("/") + "/" + os.path.basename(o) for o in ops]
    return ops[-1:] if len(ops) > 1 else []


def replaces_settings_link(scan):
    if "settings.json" not in scan:
        return False
    for words, _, _ in scan_commands(scan):
        words = strip_prefix(words)
        if not words:
            continue
        name, args = os.path.basename(words[0]), words[1:]
        if name in ("mv", "install", "ln"):
            hit = any(is_settings_link(d) for d in destinations(args))
        elif name == "cp":
            hit = "--remove-destination" in args and any(
                is_settings_link(d) for d in destinations(args))
        elif name == "sed":
            hit = (any(in_place_flag(a, "efl") for a in args)
                   and "--follow-symlinks" not in args
                   and any(is_settings_link(a) for a in args))
        elif name == "perl":
            hit = (any(in_place_flag(a, "e") for a in args)
                   and any(is_settings_link(a) for a in args))
        else:
            hit = False
        if hit:
            return True
    return False


# ---- main ----

def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return 0
        command = (data.get("tool_input") or {}).get("command")
        if not isinstance(command, str):
            raise TypeError("tool_input.command is missing or not a string")
        expanded = []
        scan = strip_heredocs(command, expanded)
        # The heredoc body of `python3 - <<EOF` is the code guard 2 must read,
        # so it scans the raw command, but only when a Python command runs.
        path = reads_after_truncate(command) if runs_python(scan) else None
        if path is not None:
            print(f"BLOCKED: '{command[:200]}' opens {path} for writing and reads it "
                  "in the same statement. The write-mode open truncates the file "
                  "before the read runs, so the file ends up empty. Read into a "
                  "variable first, then write: `s = open(p).read()` then "
                  "`open(p, 'w').write(f(s))`.", file=sys.stderr)
            return 2
        if bare_rg(scan):
            print(f"BLOCKED: '{command[:200]}' runs rg with no path. The harness's "
                  "stdin is neither a tty nor /dev/null, so rg reads stdin and the "
                  "call hangs until its timeout. Pass a path (`rg <pattern> .`) or "
                  "use `git grep <pattern>`.", file=sys.stderr)
            return 2
        if replaces_settings_link(scan):
            print(f"BLOCKED: '{command[:200]}' replaces the symlink "
                  "~/.claude/settings.json, which points into "
                  "~/.agents/skills/flow/claude/settings.json: the new plain file "
                  "detaches the live config from the repo. Edit it in place "
                  "instead: the Edit tool on the file, `cp` or a redirect "
                  "(both write through the link), or `sed -i --follow-symlinks`.",
                  file=sys.stderr)
            return 2
        ticks = backtick_bodies(scan) if "`" in scan else []
        ticks += re.findall(r"(?<!\\)`([^`]*)`", "\n".join(expanded))
        if ticks:
            print(f"BLOCKED: '{command[:200]}' uses a backtick command substitution. "
                  "Claude Code's built-in safety check cannot parse it and refuses "
                  "the whole call as a possible dangerous rm, even when nothing is "
                  "removed. Write each `cmd` as $(cmd), for example "
                  f"`{ticks[0][:80]}` -> $({ticks[0][:80]}).", file=sys.stderr)
            return 2
        return 0
    except Exception as e:  # noqa: BLE001 — the guard's own fault is reported, never silent
        print(json.dumps({"systemMessage": f"block-footguns.py: guard did not run: {type(e).__name__}: {e}"}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
