#!/usr/bin/env python3
"""Review ledger (#1262 slice 1, #1265): one JSONL row per review run, and a
per-review-type value table.

    review_ledger.py harvest [--cache DIR] [--ledger PATH] [--review-file PATH]
    review_ledger.py report  [--ledger PATH] [--weights FILE] [--split 1/k|none]
                             [--format md|json]

`harvest` reads the findings and dispositions sidecars under a review cache
(the layout `tally_review_axes.py` reads) and writes one row per axis run for
standards, spec, correctness and verification, plus an over-engineering row
holding the standards report's `OE` findings. It joins each finding's outcome
from `dispositions-<n>.jsonl` and its severity from the findings sidecar by id,
normalises drifted outcome labels, and marks each finding unique or shared
across the reviewers on the same ticket. Every label mapping, unmapped value,
overlap match and unjoinable disposition goes to the review file. Rows are
keyed by row id, so harvesting the same tree twice rewrites the same rows.

Cost fields are `unknown` here (slice 2 fills them); nothing is ever zero
because it could not be read. Severity weights and the overlap split live in
`report`, never in the ledger, so changing either needs no reharvest.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from tally_review_axes import ALL_AXES, REVIEWS_ROOT, fold_repo

DEFAULT_LEDGER = REVIEWS_ROOT / "ledger.jsonl"

# Report order. Mutation and Codex types have no harvested rows in this slice.
REVIEW_TYPES = (
    "standards", "spec", "correctness", "over-engineering", "verification",
    "witness-mutation", "call-site-mutation", "codex-gate", "codex-second",
    "codex-third", "worker-mutation",
)
MUTATION_TYPES = ("witness-mutation", "call-site-mutation", "worker-mutation")

DEFAULT_WEIGHTS = {"hard": 3, "judgement": 1, "high": 3, "medium": 2, "low": 1}
VALUE_OUTCOMES = ("fixed", "filed")
CANONICAL_OUTCOMES = ("fixed", "disputed", "filed", "handed-back", "leftover")
# Drifted label -> canonical outcome, plus whether it flags a partial fix.
PARTIAL_LABELS = {"partial": "fixed", "fixed-partial": "fixed"}
NOT_FIXED_LABELS = ("not-fixed", "not_fixed")

# Two findings on one ticket are the same finding when their files are equal
# and the word sets of their normalised titles overlap at least this much.
TITLE_MATCH_JACCARD = 0.5

_FINDINGS_RE = re.compile(
    rf"^findings-({'|'.join(ALL_AXES)}|verify|verification)-(\d+)\.jsonl$")
_DISPOSITIONS_RE = re.compile(r"^dispositions-(\d+)\.jsonl$")

_UNKNOWN_COST = {
    field: {"status": "unknown", "reason": "cost reader is slice 2 (#1262)"}
    for field in ("tokens", "wall_clock", "usage_delta")
}


def _read_jsonl(path: Path, skipped: list) -> list[dict]:
    """Every dict line of `path`; a bad line is recorded in `skipped`, not lost."""
    try:
        text = path.read_text()
    except UnicodeDecodeError as e:
        skipped.append(f"{path}: undecodable ({e})")
        return []
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            out.append(obj)
        else:
            skipped.append(f"{path}:{n}: not a JSON object")
    return out


def normalise_outcome(disp: dict) -> tuple[str, bool, dict, dict | None]:
    """(outcome, partial, outcome_status, mapping) for one dispositions line."""
    label = disp.get("outcome")
    if label in CANONICAL_OUTCOMES:
        return label, False, {"status": "known"}, None
    if label in PARTIAL_LABELS:
        return PARTIAL_LABELS[label], True, {"status": "known"}, {"from": label, "to": "fixed+partial"}
    if label in NOT_FIXED_LABELS:
        if disp.get("reason"):
            to = "disputed"
        elif disp.get("text"):
            to = "leftover"
        else:
            return "unknown", False, {
                "status": "unknown",
                "reason": f"{label!r} has neither a reason (disputed) nor a text (leftover)"}, \
                {"from": label, "to": "unknown"}
        return to, False, {"status": "known"}, {"from": label, "to": to}
    return "unknown", False, {
        "status": "unknown", "reason": f"unmapped outcome {label!r}"}, \
        {"from": str(label), "to": "unknown"}


def _tokens(title: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9]+", title.lower()))


def _same_file(a: str, b: str) -> bool:
    return a.removeprefix("./") == b.removeprefix("./")


def titles_match(a: dict, b: dict) -> bool:
    ta, tb = _tokens(a["title"]), _tokens(b["title"])
    if not (ta and tb and _same_file(a["file"], b["file"])):
        return False
    return len(ta & tb) / len(ta | tb) >= TITLE_MATCH_JACCARD


def _reviewer(row_type: str) -> str:
    """The reviewer that wrote a row: OE findings come from the standards run."""
    return "standards" if row_type == "over-engineering" else row_type


def mark_overlap(rows: list[dict], matches: list[dict]) -> None:
    """Set overlap/k on every finding; append each cross-reviewer match to `matches`."""
    by_ticket: dict[tuple, list[tuple[dict, dict]]] = {}
    for row in rows:
        for f in row["findings"]:
            by_ticket.setdefault((row["repo"], row["ticket"]), []).append((row, f))
    for (repo, ticket), items in sorted(by_ticket.items()):
        parent = list(range(len(items)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (ri, fi), (rj, fj) = items[i], items[j]
                if _reviewer(ri["type"]) != _reviewer(rj["type"]) and titles_match(fi, fj):
                    parent[find(i)] = find(j)
                    matches.append({"repo": repo, "ticket": ticket, "file": fi["file"],
                                    "a": (ri["type"], fi["id"], fi["title"]),
                                    "b": (rj["type"], fj["id"], fj["title"])})
        clusters: dict[int, set] = {}
        for i, (row, _) in enumerate(items):
            clusters.setdefault(find(i), set()).add(_reviewer(row["type"]))
        for i, (_, f) in enumerate(items):
            k = len(clusters[find(i)])
            f["overlap"], f["k"] = ("shared" if k > 1 else "unique"), k


def harvest_cache(cache: Path) -> tuple[list[dict], dict]:
    """(rows, review-file facts) for a whole cache tree."""
    if not cache.is_dir():
        raise FileNotFoundError(f"review cache not found: {cache}")
    rows: list[dict] = []
    seen_ids: set[str] = set()
    mappings: Counter = Counter()
    unmapped: Counter = Counter()
    orphans: list[str] = []
    skipped: list[str] = []
    for repo_dir in sorted(p for p in cache.iterdir() if p.is_dir() and not p.name.startswith("scratch")):
        repo = fold_repo(repo_dir.name)
        dispositions: dict[int, dict[str, dict]] = {}
        for path in sorted(repo_dir.glob("dispositions-*.jsonl")):
            m = _DISPOSITIONS_RE.match(path.name)
            if m:
                dispositions[int(m.group(1))] = {
                    d["id"]: d for d in _read_jsonl(path, skipped) if isinstance(d.get("id"), str)}
        joined: set[tuple[int, str]] = set()
        for path in sorted(repo_dir.glob("findings-*.jsonl")):
            m = _FINDINGS_RE.match(path.name)
            if not m:
                continue
            axis, ticket = m.group(1), int(m.group(2))
            if axis == "verify":
                mappings["verify -> verification (axis in filename)"] += 1
            base = "verification" if axis in ("verify", "verification") else axis
            by_type: dict[str, list] = {base: []}
            file_dispositions = dispositions.get(ticket)
            row_mappings: dict[str, list] = {}
            for raw in _read_jsonl(path, skipped):
                if not all(isinstance(raw.get(k), str) and raw[k] for k in ("id", "severity", "file", "title")):
                    skipped.append(f"{path}: finding without id/severity/file/title")
                    continue
                row_type = "over-engineering" if base == "standards" and raw["id"].startswith("OE") else base
                if file_dispositions is None:
                    outcome, partial, status, mapping = "unknown", False, {
                        "status": "unknown", "reason": f"no dispositions file for ticket {ticket}"}, None
                elif raw["id"] not in file_dispositions:
                    outcome, partial, status, mapping = "unknown", False, {
                        "status": "unknown", "reason": f"no disposition line for {raw['id']}"}, None
                else:
                    joined.add((ticket, raw["id"]))
                    outcome, partial, status, mapping = normalise_outcome(file_dispositions[raw["id"]])
                if mapping:
                    (unmapped if mapping["to"] == "unknown" else mappings)[
                        f"{mapping['from']} -> {mapping['to']}"] += 1
                    row_mappings.setdefault(row_type, []).append(mapping)
                by_type.setdefault(row_type, []).append({
                    "id": raw["id"], "severity": raw["severity"], "severity_status": {"status": "known"},
                    "outcome": outcome, "outcome_status": status, "partial": partial,
                    "file": raw["file"], "title": raw["title"]})
            for row_type, findings in by_type.items():
                if row_type == "over-engineering" and not findings:
                    continue
                stem = path.stem
                row_id = f"{repo}/{ticket}/{row_type}/1/{stem}"
                if row_id in seen_ids:
                    row_id = f"{repo}/{ticket}/{row_type}/1/{repo_dir.name}:{stem}"
                seen_ids.add(row_id)
                sources = [f"{repo_dir.name}/{path.name}"]
                if file_dispositions is not None:
                    sources.append(f"{repo_dir.name}/dispositions-{ticket}.jsonl")
                rows.append({
                    "row_id": row_id, "repo": repo, "pr": None, "ticket": ticket, "tickets": [ticket],
                    "type": row_type, "round": 1, "run_id": row_id.split("/", 4)[4], "model": None,
                    "findings": findings, "cost": _UNKNOWN_COST,
                    "status": {
                        "fields": {"pr": {"status": "unknown", "reason": "not in the sidecars"},
                                   "model": {"status": "unknown", "reason": "not in the sidecars"},
                                   "findings": {"status": "known"}},
                        "sources": sources, "mappings": row_mappings.get(row_type, [])}})
        for ticket, table in sorted(dispositions.items()):
            for fid in sorted(table):
                if (ticket, fid) not in joined:
                    orphans.append(f"{repo_dir.name} #{ticket} `{fid}` ({table[fid].get('outcome')})")
    rows.sort(key=lambda r: r["row_id"])
    matches: list[dict] = []
    mark_overlap(rows, matches)
    return rows, {"mappings": mappings, "unmapped": unmapped, "matches": matches,
                  "orphans": sorted(set(orphans)), "skipped": sorted(set(skipped))}


def review_file_text(facts: dict) -> str:
    def table(counter):
        return "\n".join(f"- `{k.split(' -> ')[0]}` -> {k.split(' -> ', 1)[1]}: {n}"
                         for k, n in sorted(counter.items())) or "- none"

    matches = "\n".join(
        f"- {m['repo']} #{m['ticket']} `{m['file']}`: {m['a'][0]} {m['a'][1]} \"{m['a'][2]}\""
        f" = {m['b'][0]} {m['b'][1]} \"{m['b'][2]}\""
        for m in sorted(facts["matches"], key=lambda m: (m["repo"], m["ticket"], m["a"], m["b"]))) or "- none"
    return "\n".join([
        "# Review ledger harvest: review file", "",
        "## Label mappings applied", table(facts["mappings"]), "",
        "## Unmapped values", table(facts["unmapped"]), "",
        f"## Overlap matches ({len(facts['matches'])})", matches, "",
        "## Dispositions with no finding",
        "\n".join(f"- {o}" for o in facts["orphans"]) or "- none", "",
        "## Skipped lines", "\n".join(f"- {s}" for s in facts["skipped"]) or "- none", ""])


def cmd_harvest(args) -> int:
    try:
        rows, facts = harvest_cache(args.cache)
    except FileNotFoundError as e:
        print(f"review_ledger: {e}", file=sys.stderr)
        return 2
    existing = {}
    if args.ledger.exists():
        existing = {r["row_id"]: r for r in map(json.loads, args.ledger.read_text().splitlines()) if r}
    existing.update({r["row_id"]: r for r in rows})
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.write_text("".join(json.dumps(existing[k], sort_keys=True) + "\n" for k in sorted(existing)))
    review = args.review_file or args.ledger.with_suffix(".review.md")
    review.write_text(review_file_text(facts))
    print(f"harvested {len(rows)} rows into {args.ledger}; "
          f"{sum(facts['unmapped'].values())} unmapped values, {len(facts['matches'])} overlap matches "
          f"listed in {review}")
    return 0


def summarise(rows: list[dict], weights: dict, split: str) -> dict:
    types = []
    for t in REVIEW_TYPES:
        mine = [r for r in rows if r["type"] == t]
        if not mine:
            continue
        findings = [f for r in mine for f in r["findings"]]
        value, unweighted = 0.0, 0
        for f in findings:
            if f["outcome"] not in VALUE_OUTCOMES:
                continue
            weight = weights.get(f["severity"])
            if weight is None:
                unweighted += 1
                continue
            value += weight / (f["k"] if split == "1/k" else 1)
        known = [f for f in findings if f["outcome"] != "unknown"]
        rate = lambda outcome: (sum(f["outcome"] == outcome for f in known) / len(known)) if known else None
        types.append({
            "type": t, "rows": len(mine), "findings": len(findings), "value": round(value, 4),
            "unique_share": (sum(f["overlap"] == "unique" for f in findings) / len(findings)) if findings else None,
            "leftover_rate": rate("leftover"), "dispute_rate": rate("disputed"),
            "unknown_outcomes": len(findings) - len(known), "unweighted": unweighted,
            "unknown_cost_rows": sum(
                any(v.get("status") == "unknown" for v in r["cost"].values()) for r in mine)})
    notes = [f"No mutation rows: harvest writes none ({', '.join(MUTATION_TYPES)}); nothing on disk "
             "records them in a form a script can read."]
    return {"types": types, "notes": notes}


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def cmd_report(args) -> int:
    if not args.ledger.exists():
        print(f"review_ledger: ledger not found: {args.ledger}", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in args.ledger.read_text().splitlines() if line.strip()]
    weights = json.loads(args.weights.read_text()) if args.weights else DEFAULT_WEIGHTS
    result = summarise(rows, weights, args.split)
    if args.format == "json":
        print(json.dumps(result, indent=2))
        return 0
    print("| type | rows | findings | value | unique share | leftover rate | dispute rate "
          "| unknown outcomes | unweighted | unknown-cost rows |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for t in result["types"]:
        print(f"| {t['type']} | {t['rows']} | {t['findings']} | {t['value']:.2f} | {_pct(t['unique_share'])} "
              f"| {_pct(t['leftover_rate'])} | {_pct(t['dispute_rate'])} | {t['unknown_outcomes']} "
              f"| {t['unweighted']} | {t['unknown_cost_rows']} |")
    print()
    for note in result["notes"]:
        print(note)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("--cache", type=Path, default=REVIEWS_ROOT)
    h.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    h.add_argument("--review-file", type=Path)
    h.set_defaults(func=cmd_harvest)
    r = sub.add_parser("report")
    r.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    r.add_argument("--weights", type=Path)
    r.add_argument("--split", choices=("1/k", "none"), default="1/k")
    r.add_argument("--format", choices=("md", "json"), default="md")
    r.set_defaults(func=cmd_report)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
