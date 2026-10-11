#!/usr/bin/env python3
"""PROTOTYPE — throwaway, not production. Ticket #604.

Question: what does "verify a claim about code" mean as a procedure? How
much of it is a mechanical lookup, and how much needs a reader?

The procedure tried here:
  1. A claim is a doc line that names code: an inline `backticked` token, or
     a number next to a plural noun ("14 tests").
  2. Each token gets a kind (path, identifier, route, command, word, phrase).
  3. Each kind has one mechanical check against the tracked non-Markdown
     tree. A token the tree does not hold is a FALSE candidate.
  4. A line that relates two code tokens with a verb (imports, calls, reads,
     on restart ...) is a relation: it goes to a reader with a hint.
  5. Counts go to a reader; nothing mechanical knows what was counted.

Run:  python3 sweep_prototype.py <repo> <doc.md> [<doc.md> ...]
Read-only on <repo>. Prints the split by kind and verdict, then every
FALSE candidate and every reader item as file:line.
"""
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

EXT = (r"mjs|js|cjs|ts|md|json|cs|sh|html|css|txt|bat|ps1|py|png|exe|yml|"
       r"yaml|toml|lock|log|svg|jpg|wav|mp3")
RELATION = re.compile(
    r"\b(imports?|imported by|calls?|called by|callers?|exports?|reads?|"
    r"writes?|spawns?|launch(es)?|restarts?|on restart|deletes?|owns?|"
    r"wraps?|returns?|throws?|only caller|never)\b", re.I)
GONE = re.compile(
    r"\b(renamed|retired|removed|deleted|dropped|replaced|no longer|used to|"
    r"gone|formerly|was called|superseded)\b", re.I)
COUNT = re.compile(r"\b(\d{1,5})\s+([a-z][a-z-]+s)\b")
COMMANDS = ("npm", "node", "git", "bash", "gh", "uv", "python3", "npx", "sh")
STOP = {"true", "false", "null", "undefined", "main", "origin"}


def tracked(repo):
    out = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True,
                         text=True).stdout.split("\n")
    return [f for f in out if f]


def load_corpus(repo, files):
    """Tracked non-Markdown text, by file: what a claim is checked against."""
    corpus = {}
    for f in files:
        p = repo / f
        if f.endswith(".md") or not p.is_file() or p.stat().st_size > 1_000_000:
            continue
        try:
            corpus[f] = p.read_text()
        except UnicodeDecodeError:
            pass
    return corpus


def kind_of(tok):
    if "<" in tok or "…" in tok or "..." in tok:
        return "placeholder"
    if " " in tok:
        return "command" if tok.split()[0] in COMMANDS else "phrase"
    if re.fullmatch(r"/[\w\-/:.]+", tok) and not re.search(rf"\.({EXT})$", tok):
        return "route"
    if re.fullmatch(rf"[\w.\-/*~]+\.({EXT})", tok) or (
            "/" in tok and re.fullmatch(r"[\w.\-/*~]+", tok)):
        return "path"
    core = tok.rstrip("()").lstrip(".")
    if re.fullmatch(r"[A-Za-z_$][\w$]*(\.[\w$]+)*", core):
        humped = (re.search(r"[a-z][A-Z]|_|\.", core) or core.isupper()
                  or tok.endswith("()"))
        return "identifier" if humped else "word"
    return "literal"


def in_corpus(needle, corpus, word=False):
    pat = re.compile(rf"(?<![\w$]){re.escape(needle)}(?![\w$])") if word else None
    return [f for f, text in corpus.items()
            if (pat.search(text) if word else needle in text)]


def check(tok, kind, repo, doc, files, corpus):
    """(verdict, note). ABSENT/MISSING are the FALSE candidates."""
    if kind == "path":
        clean = tok.lstrip("~/") if tok.startswith("~") else tok
        if tok.startswith("~") or tok.startswith("/"):
            return "skip", "outside the repo"
        hits = ([f for f in files if Path(f).match(clean)] if "*" in clean else
                [f for f in files if f == clean or f.endswith("/" + clean)
                 or f.startswith(clean.rstrip("/") + "/")])
        if hits or (repo / clean).exists() or (doc.parent / clean).exists():
            return "ok", ""
        if in_corpus(Path(clean).name, corpus):
            return "ok", "named in code, not a tracked file"
        return "MISSING", "no tracked or on-disk path matches"
    if kind == "identifier":
        core = tok.rstrip("()").lstrip(".")
        last = core.split(".")[-1]
        hits = in_corpus(core, corpus, word=True) or in_corpus(last, corpus,
                                                               word=True)
        if not hits:
            return "ABSENT", "name appears in no tracked non-Markdown file"
        if all(".test." in f or f.startswith(("e2e", "tests/")) for f in hits):
            return "ok", f"tests only ({len(hits)} files)"
        return "ok", ""
    if kind in ("route", "word", "literal", "phrase"):
        if tok in STOP or len(tok) < 3:
            return "skip", "too generic"
        hits = in_corpus(tok, corpus, word=(kind == "word"))
        return ("ok", "") if hits else ("ABSENT", "string appears in no "
                                        "tracked non-Markdown file")
    if kind == "command":
        m = re.match(r"npm (?:run )?([\w:\-]+)", tok)
        if m and m.group(1) not in ("install", "ci", "test", "run"):
            ok = f'"{m.group(1)}"' in corpus.get("package.json", "")
            return ("ok", "") if ok else ("ABSENT", "no such npm script")
        args = [a for a in tok.split()[1:] if re.search(rf"\.({EXT})$", a)]
        gone = [a for a in args if not (repo / a).exists()]
        return ("MISSING", f"file argument gone: {gone[0]}") if gone else ("ok", "")
    return "skip", kind


def main():
    repo = Path(sys.argv[1]).resolve()
    docs = [Path(d) if Path(d).is_absolute() else repo / d for d in sys.argv[2:]]
    files = tracked(repo)
    corpus = load_corpus(repo, files)
    rows, relations, counts = [], [], []
    for doc in docs:
        fenced = False
        for n, line in enumerate(doc.read_text().splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            where = f"{doc.relative_to(repo)}:{n}"
            toks = re.findall(r"`([^`\n]+)`", line)
            for tok in toks:
                kind = kind_of(tok.strip())
                verdict, note = check(tok.strip(), kind, repo, doc, files, corpus)
                gone = bool(GONE.search(line))
                if gone and verdict in ("ABSENT", "MISSING"):
                    verdict, note = "ok", "gone, as the line says"
                elif gone and verdict == "ok" and kind in ("identifier", "path"):
                    note = "SAID-GONE line, still present"
                rows.append((where, tok.strip(), kind, verdict, note))
            prose = re.sub(r"`[^`]*`", "", line)
            if len(toks) >= 2 and RELATION.search(prose):
                held = [t for t in toks if t in corpus]
                hint = "; ".join(
                    f"{h} {'holds' if re.search(re.escape(Path(t).stem if '.' in t else t.rstrip('()')), corpus[h]) else 'LACKS'} {t}"
                    for h in held for t in toks if t != h)
                relations.append((where, RELATION.search(prose).group(0), toks,
                                  line.strip() + ("\n      hint: " + hint if hint else "")))
            for m in COUNT.finditer(prose):
                counts.append((where, m.group(0), line.strip()))

    print(f"repo {repo}   {len(docs)} docs   {len(corpus)} tracked non-Markdown "
          f"files checked against\n")
    print("TOKENS BY KIND AND VERDICT")
    table = Counter((k, v) for _, _, k, v, _ in rows)
    verdicts = ["ok", "ABSENT", "MISSING", "skip"]
    print(f"  {'kind':<12}" + "".join(f"{v:>9}" for v in verdicts))
    for kind in sorted({k for k, _ in table}):
        print(f"  {kind:<12}" + "".join(f"{table[(kind, v)]:>9}" for v in verdicts))
    false = [r for r in rows if r[3] in ("ABSENT", "MISSING")]
    seen = len({(r[1], r[3]) for r in false})
    print(f"\n  {len(rows)} tokens, {len(false)} FALSE candidates "
          f"({seen} distinct), {len(relations)} relation lines for a reader, "
          f"{len(counts)} counts for a reader\n")

    print("FALSE CANDIDATES (mechanical)")
    for where, tok, kind, verdict, note in false:
        print(f"  {where:<34} {verdict:<8} {kind:<10} `{tok}` — {note}")
    print("\nTESTS-ONLY NAMES (a doc names it as live code; only tests hold it)")
    for where, tok, kind, verdict, note in rows:
        if note.startswith("tests only"):
            print(f"  {where:<34} `{tok}` — {note}")
    print("\nSAID-GONE BUT PRESENT (the line says it left; the tree still holds it)")
    for where, tok, kind, verdict, note in rows:
        if note.startswith("SAID-GONE"):
            print(f"  {where:<34} `{tok}`")
    print("\nRELATIONS (a reader checks: does the tree agree with the verb?)")
    for where, verb, toks, line in relations:
        print(f"  {where:<34} [{verb}] {' , '.join(toks[:4])}\n      {line[:400]}")
    print("\nCOUNTS (a reader re-counts)")
    for where, what, line in counts:
        print(f"  {where:<34} {what:<22} {line[:110]}")


if __name__ == "__main__":
    main()
