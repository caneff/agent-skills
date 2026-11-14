"""The audit record's body (#1680): what `driver.py multi` files as one issue
per repo, built from facts the sweep left on disk. No model writes or merges
any of it; this module only formats and splits.

`build` returns the issue body followed by the comments that continue it. Every
chunk is at most GitHub's 65,536-character limit, a finding is never cut in two
unless it alone exceeds a chunk, and the chunks in order hold every finding once.
"""
import dataclasses
import html.parser
import json

LIMIT = 65536
_PREFIX_ROOM = 120  # the "(continued)" line a comment starts with

# Summarised by their report headings: these three write no findings.jsonl.
STRUCTURAL = ("ponytail-audit", "thermo-nuclear-code-quality-review", "improve-codebase-architecture")


@dataclasses.dataclass
class RecordModel:
    """One record: everything one sweep of one repo left on disk, which `build`
    turns into one issue body and its continuation comments. Plain data; the
    fields say what each holds.
    """
    sweep_id: str
    timestamp: str
    sha: str
    clean: str                  # "yes" or "no (...)"
    stored_path: str
    ran: list                   # audits the sweep ran this time, in order
    # audit -> the earlier sha its cached report was made at
    skipped: dict
    failed: dict                # audit -> error tail
    # audit -> list of parsed rows (dict) or raw lines (str)
    findings: dict
    # audit -> manifest summary, for an audit that wrote no findings.jsonl
    no_log: dict
    suppressed: int
    # audits that ran but gave no suppressed count, when an ignore file exists
    suppression_unreported: list
    headings: dict              # structural audit -> report headings
    synthesis: str
    # url of an earlier record still open when this sweep was forced
    open_record: str = ""
    # url of the newest earlier record, where skipped audits' findings went
    earlier_record: str = ""


def finding_count(model):
    return sum(len(rows) for rows in model.findings.values())


def worth_filing(model):
    """A repo with a finding, a failed audit, or an audit whose manifest counts
    findings but wrote no log has something to decide. Anything else files
    nothing."""
    unlogged = any(info.get("count") for info in model.no_log.values())
    return bool(finding_count(model) or model.failed or unlogged)


class _Headings(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.found, self._open = [], None

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3"):
            self._open = []

    def handle_data(self, data):
        if self._open is not None:
            self._open.append(data)

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3") and self._open is not None:
            text = " ".join("".join(self._open).split())
            if text:
                self.found.append(text)
            self._open = None


def report_headings(html_text):
    """The text of every `h1`, `h2` and `h3` in `html_text`, in document order,
    as a list of strings with whitespace collapsed. A heading with no text is
    left out; an HTML with no heading gives `[]`."""
    parser = _Headings()
    parser.feed(html_text)
    return parser.found


def _indent(text, pad="  "):
    return ("\n" + pad).join(str(text).splitlines() or [""])


def render_finding(row):
    if isinstance(row, str):
        return f"- unparseable line in findings.jsonl, kept verbatim: `{row}`"
    if "summary" not in row:
        return f"- finding row without a summary, kept verbatim: `{json.dumps(row, sort_keys=True)}`"
    where = f"{row.get('file', '?')}:{row.get('line', '?')}"
    tag = "/".join(str(row[k]) for k in ("bucket", "category") if row.get(k))
    lines = [f"- `{where}` — {_indent(row['summary'])}" + (f" [{tag}]" if tag else "")]
    if row.get("failure"):
        lines.append(f"  - Problem: {_indent(row['failure'], '    ')}")
    if row.get("after"):
        lines.append(f"  - Suggestion: {_indent(row['after'], '    ')}")
    return "\n".join(lines)


def _blocks(model):
    """The body as atomic blocks: the packer never cuts inside one."""
    out = [
        "# Audit record\n\n"
        f"- Sweep: {model.sweep_id}\n- Time: {model.timestamp}\n- Audited commit: {model.sha}\n"
        f"- Worktree clean: {model.clean}\n- Stored sweep: {model.stored_path}",
        "## Audits\n\n"
        f"Audits run: {', '.join(model.ran) or 'none'}",
    ]
    if model.open_record:
        out[0] += f"\n- Earlier open audit record: {model.open_record}"
    if model.skipped:
        out.append("## Skipped as unchanged\n\nTheir findings are not copied in: they were recorded when the earlier report was made.\n\n"
                   + "\n".join(f"- {n}: unchanged since {sha}" for n, sha in model.skipped.items())
                   + (f"\n\nEarlier audit record: {model.earlier_record}" if model.earlier_record else ""))
    if model.failed:
        out.append("## Failed audits\n\n" + "\n\n".join(
            f"### {n} failed\n\n```\n{tail}\n```" for n, tail in model.failed.items()))
    note = f" (no count from: {', '.join(model.suppression_unreported)})" if model.suppression_unreported else ""
    out.append(f"Suppressed by .audit-ignore.md: {model.suppressed}{note}")
    out.append(f"## Findings ({finding_count(model)})")
    if model.no_log:
        out.append("Audits with no findings.jsonl:\n\n" + "\n".join(
            f"- {n}: manifest count {info.get('count', '?')}, {info.get('headline', 'no headline')}"
            for n, info in model.no_log.items()))
    for name, rows in model.findings.items():
        out.append(f"### {name}\n")
        out.extend(render_finding(r) for r in rows)
    if model.headings:
        out.append("## Structural audits\n\n" + "\n\n".join(
            f"### {n} (report headings)\n\n" + "\n".join(f"- {h}" for h in heads)
            for n, heads in model.headings.items()))
    out.append("## Synthesis\n\n" + (model.synthesis or "none: the synthesis pass wrote nothing"))
    return out


def _pack(blocks, budget):
    chunks, cur = [], ""
    for block in blocks:
        while len(block) > budget:  # one block alone past a chunk: cut it, never drop it
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(block[:budget])
            block = block[budget:]
        if cur and len(cur) + 2 + len(block) > budget:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        chunks.append(cur)
    return chunks


def build(model):
    """[body, comment, comment, ...], each within LIMIT."""
    chunks = _pack(_blocks(model), LIMIT - _PREFIX_ROOM)
    total = len(chunks)
    return [chunks[0]] + [f"Audit record, continued (part {i + 1} of {total}).\n\n{c}" for i, c in enumerate(chunks[1:], 1)]
