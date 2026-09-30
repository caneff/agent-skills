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
keyed by row id, so harvesting the same tree twice rewrites the same rows; a
harvest replaces every earlier harvest row and keeps rows written any other way.
A sidecar whose name is off the harvested patterns, an unreadable line and an
empty sidecar are listed or marked `unknown`, never dropped or read as clean.

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
from datetime import datetime
from pathlib import Path

from tally_review_axes import (
    _OUTCOME_DETAIL_FIELD, ALL_AXES, REVIEWS_ROOT, find_sidecar_files, fold_repo, load_jsonl,
    parse_disposition_sidecar_filename, parse_finding_sidecar_filename)

DEFAULT_LEDGER = REVIEWS_ROOT / "ledger.jsonl"
DEFAULT_TRANSCRIPTS = Path.home() / ".claude" / "projects"
TOKEN_KINDS = ("input", "output", "cache_write", "cache_read")
_USAGE_FIELDS = {"input": "input_tokens", "output": "output_tokens",
                 "cache_write": "cache_creation_input_tokens", "cache_read": "cache_read_input_tokens"}

# Report order. Mutation and Codex types have no harvested rows in this slice.
REVIEW_TYPES = (
    "standards", "spec", "correctness", "over-engineering", "verification",
    "witness-mutation", "call-site-mutation", "codex-gate", "codex-second",
    "codex-third", "worker-mutation",
)
MUTATION_TYPES = ("witness-mutation", "call-site-mutation", "worker-mutation")

DEFAULT_WEIGHTS = {"hard": 3, "judgement": 1, "high": 3, "medium": 2, "low": 1}
VALUE_OUTCOMES = ("fixed", "filed")
# Drifted label -> canonical outcome, plus whether it flags a partial fix.
PARTIAL_LABELS = {"partial": "fixed", "fixed-partial": "fixed"}
NOT_FIXED_LABELS = ("not-fixed", "not_fixed")
# A not-fixed row is a dispute when its own words say the finding was wrong,
# and a leftover when they say the fix did not land; no words at all is unknown.
DISPUTE_MARKERS = ("dispute", "false positive", "unreachable", "not a bug", "by design", "wontfix")

# Two findings on one ticket are the same finding when their files are equal
# and the word sets of their normalised titles overlap at least this much.
TITLE_MATCH_JACCARD = 0.5

# The findings sidecar names `parse_finding_sidecar_filename` does not accept:
# the verification axis, a multi-ticket clump (`975-983`) and a round suffix
# (`-r2`, `-round1`). A name matching neither is listed, never dropped.
_EXTRA_FINDINGS_RE = re.compile(
    rf"^findings-({'|'.join(ALL_AXES)}|verify|verification)-(\d+(?:-\d+)*?)(?:-(?:r|round)(\d+))?\.jsonl$")
_MULTI_DISPOSITIONS_RE = re.compile(r"^dispositions-(\d+(?:-\d+)+)\.jsonl$")
_OE_ID_RE = re.compile(r"^(?:r\d+-)?OE\d")
_ROUND_ID_RE = re.compile(r"^r(\d+)-")

_NOT_APPLICABLE = {"status": "not-applicable", "reason": "Codex only; this is a Claude reviewer"}
_INSIDE_STANDARDS = {"status": "inside-standards",
                     "reason": "over-engineering is written by the standards run; its cost is in that row"}


def unknown_cost(reason: str) -> dict:
    return {"tokens": {"status": "unknown", "reason": reason},
            "wall_clock": {"status": "unknown", "reason": reason},
            "usage_delta": dict(_NOT_APPLICABLE)}


# A subagent transcript lives at <projects>/<project>/<session>/subagents/agent-<id>.{jsonl,meta.json}, and
# <project> is the working directory with "/" and "/." both written "-" and "--".
_PROJECT_RE = re.compile(
    r"^-home-[^-]+(?:-src-(?P<src>.+?)|--agents-(?P<agents>.+?))(?:--claude-worktrees-implement-(?P<n>\d+))?$")
_REVIEW_AXES = ("standards", "spec", "correctness")


def _axis_of(text: str) -> str | None:
    """The one review type a phrase names, or None when it names none or several."""
    low = text.lower()
    if "verif" in low:
        return "verification"
    found = [a for a in _REVIEW_AXES if a in low]
    return found[0] if len(found) == 1 else None


def _first_text(obj: dict) -> str | None:
    content = (obj.get("message") or {}).get("content") if isinstance(obj.get("message"), dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return None


def read_transcript(path: Path) -> dict:
    """The first user message, model, token totals and wall clock of one transcript.
    A streamed message is written as several lines sharing an id, each with the usage so
    far, so each token kind takes its maximum per id. A cache kind a usage block leaves
    out counts as none (the API omits it when nothing was cached); a missing block, or an
    unreadable line that could have held one, leaves the tokens unknown."""
    per_id: dict[str, dict] = {}
    stamps: list[tuple[datetime, str]] = []
    models: Counter = Counter()
    first, lost = None, 0
    for n, raw in enumerate(path.read_text(errors="replace").splitlines()):
        if not raw.strip():
            continue
        obj = _dict_line(raw)
        if obj is None:
            lost += 1
            continue
        ts = obj.get("timestamp")
        if isinstance(ts, str):
            try:
                stamps.append((datetime.fromisoformat(ts.replace("Z", "+00:00")), ts))
            except ValueError:
                pass
        if first is None and obj.get("type") == "user":
            first = _first_text(obj)
        msg = obj.get("message")
        if obj.get("type") != "assistant" or not isinstance(msg, dict):
            continue
        if isinstance(msg.get("model"), str):
            models[msg["model"]] += 1
        u = msg.get("usage")
        if isinstance(u, dict) and all(isinstance(u.get(_USAGE_FIELDS[k], 0), int) for k in TOKEN_KINDS) \
                and all(_USAGE_FIELDS[k] in u for k in ("input", "output")):
            mine = per_id.setdefault(str(msg.get("id") or f"line{n}"), dict.fromkeys(TOKEN_KINDS, 0))
            for k in TOKEN_KINDS:
                mine[k] = max(mine[k], u.get(_USAGE_FIELDS[k], 0))
    if lost:
        tokens = {"status": "unknown", "reason": f"{lost} unreadable line(s) in the transcript"}
    elif not per_id:
        tokens = {"status": "unknown", "reason": "transcript has no usage block"}
    else:
        tokens = {"status": "known", **{k: sum(m[k] for m in per_id.values()) for k in TOKEN_KINDS}}
    if len(stamps) < 1:
        wall = {"status": "unknown", "reason": "transcript has no readable timestamp"}
    else:
        lo, hi = min(stamps), max(stamps)
        wall = {"status": "known", "start": lo[1], "end": hi[1], "seconds": round((hi[0] - lo[0]).total_seconds(), 3)}
    return {"first": first, "model": models.most_common(1)[0][0] if models else None,
            "tokens": tokens, "wall_clock": wall}


def attribute(meta: dict, project: str, first: str | None) -> tuple[dict | None, str]:
    """(repo, ticket, type, round) of one diff-reviewer run, or (None, why not)."""
    pm = _PROJECT_RE.match(project)
    if not pm:
        return None, f"project directory {project!r} names no known repo"
    repo = fold_repo(pm.group("src") or pm.group("agents"))
    desc, head = str(meta.get("description") or ""), (first or "")
    ticket = int(pm.group("n")) if pm.group("n") else None
    if ticket is None and (m := re.search(r"#(\d+)", desc)):
        ticket = int(m.group(1))
    if ticket is None and (m := re.search(r"worktrees/implement-(\d+)", head)):
        ticket = int(m.group(1))
    if ticket is None:
        return None, "no ticket in the project directory, the description or the first message"
    by_desc = _axis_of(desc)
    header = re.search(r"axis:\s*\**\s*([a-z ]+)", head[:300].lower())
    by_head = _axis_of(header.group(1)) if header else (_axis_of(head[:200]) if not by_desc else None)
    if by_desc and by_head and by_desc != by_head:
        return None, f"description says {by_desc} but the first message says {by_head}"
    axis = by_desc or by_head
    if axis is None:
        return None, "no review axis in the description or the first message"
    rm = re.search(r"round[ -]?(\d+)", desc.lower()) or re.search(r"round[ -]?(\d+)", head[:120].lower())
    return {"repo": repo, "ticket": ticket, "type": axis, "round": int(rm.group(1)) if rm else 1}, ""


def read_transcripts(root: Path) -> tuple[list[dict], list[str], int]:
    """(attributed runs, unattributed with reasons, count of other agent types ignored)."""
    runs: list[dict] = []
    unattributed: list[str] = []
    ignored = 0
    for meta_path in sorted(root.glob("*/*/subagents/agent-*.meta.json")):
        project, agent = meta_path.parts[-4], meta_path.name.removesuffix(".meta.json")
        label = f"{project}/{agent}"
        try:
            meta = json.loads(meta_path.read_text())
            if not isinstance(meta, dict):
                raise ValueError("not an object")
        except (ValueError, OSError):
            unattributed.append(f"{label}: unreadable meta.json")
            continue
        if meta.get("agentType") != "diff-reviewer":
            ignored += 1
            continue
        path = meta_path.with_name(agent + ".jsonl")
        if not path.exists():
            unattributed.append(f"{label}: meta.json has no transcript beside it")
            continue
        read = read_transcript(path)
        key, why = attribute(meta, project, read["first"])
        if key is None:
            unattributed.append(f"{label}: {why}")
            continue
        runs.append({**key, "agent": agent, "source": f"{project}/{agent}.jsonl", "model": read["model"],
                     "tokens": read["tokens"], "wall_clock": read["wall_clock"]})
    return runs, unattributed, ignored


def _merge_cost(runs: list[dict]) -> tuple[dict, str | None]:
    """The cost of one review row from the runs attributed to it: tokens and seconds add;
    one unknown run makes that field unknown."""
    cost = {"usage_delta": dict(_NOT_APPLICABLE)}
    for field in ("tokens", "wall_clock"):
        bad = [r[field]["reason"] for r in runs if r[field]["status"] != "known"]
        if bad:
            cost[field] = {"status": "unknown", "reason": "; ".join(sorted(set(bad)))}
        elif field == "tokens":
            cost[field] = {"status": "known", **{k: sum(r[field][k] for r in runs) for k in TOKEN_KINDS}}
        else:
            cost[field] = {"status": "known", "start": min(r[field]["start"] for r in runs),
                           "end": max(r[field]["end"] for r in runs),
                           "seconds": round(sum(r[field]["seconds"] for r in runs), 3)}
    models = sorted({r["model"] for r in runs if r["model"]})
    return cost, (models[0] if len(models) == 1 else None)


def attach_costs(rows: list[dict], runs: list[dict], missing: str | None) -> list[dict]:
    """Fill each row's cost from its transcripts; returns rows for runs no sidecar row holds.
    A verification run whose round differs from its sidecar's joins that row when the ticket
    has exactly one verification row. Over-engineering cost stays inside standards."""
    by_key: dict[tuple, list[dict]] = {}
    for r in rows:
        for t in r["tickets"]:
            by_key.setdefault((r["repo"], t, r["type"], r["round"]), []).append(r)
    by_type: dict[tuple, list[dict]] = {}
    for r in rows:
        by_type.setdefault((r["repo"], r["ticket"], r["type"]), []).append(r)
    joined: dict[str, list[dict]] = {}
    extra: list[dict] = []
    for run in runs:
        hits = by_key.get((run["repo"], run["ticket"], run["type"], run["round"]), [])
        if not hits and run["type"] == "verification":
            hits = by_type.get((run["repo"], run["ticket"], "verification"), [])
            hits = hits if len(hits) == 1 else []
        if hits:
            joined.setdefault(hits[0]["row_id"], []).append(run)
            continue
        extra.append(run)
    for r in rows:
        if r["type"] == "over-engineering":
            r["cost"] = {"tokens": dict(_INSIDE_STANDARDS), "wall_clock": dict(_INSIDE_STANDARDS),
                         "usage_delta": dict(_NOT_APPLICABLE)}
        elif r["row_id"] in joined:
            r["cost"], r["model"] = _merge_cost(joined[r["row_id"]])
            if r["model"]:
                r["status"]["fields"]["model"] = {"status": "known"}
            r["status"]["sources"] += [run["source"] for run in joined[r["row_id"]]]
        else:
            r["cost"] = unknown_cost(missing or "no transcript attributed to this row")
    new_rows = []
    for run in extra:
        cost, model = _merge_cost([run])
        new_rows.append({
            "row_id": f"{run['repo']}/{run['ticket']}/{run['type']}/{run['round']}/{run['agent']}",
            "origin": "harvest", "repo": run["repo"], "pr": None, "ticket": run["ticket"],
            "tickets": [run["ticket"]], "type": run["type"], "round": run["round"], "run_id": run["agent"],
            "model": model, "findings": [], "cost": cost,
            "status": {"fields": {"pr": {"status": "unknown", "reason": "not in the transcript"},
                                  "model": {"status": "known"} if model else {"status": "unknown", "reason": "no model in the transcript"},
                                  "findings": {"status": "unknown", "reason": "no findings sidecar for this run: nothing found, or nothing written"}},
                       "sources": [run["source"]], "mappings": []}})
    return new_rows


def _dict_line(raw: str):
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _read_sidecar(path: Path, skipped: list) -> tuple[list[dict], int]:
    """(dict lines, number of unreadable lines); the loss is recorded in `skipped`."""
    rows = load_jsonl(path, _dict_line)
    nonblank = sum(1 for line in path.read_text(errors="replace").splitlines() if line.strip())
    lost = nonblank - len(rows)
    if lost:
        skipped.append(f"{path.parent.name}/{path.name}: {lost} unreadable line(s)")
    return rows, lost


def normalise_outcome(disp: dict) -> tuple[str, bool, dict, dict | None]:
    """(outcome, partial, outcome_status, mapping) for one dispositions line."""
    label = disp.get("outcome")
    if not isinstance(label, str):
        return "unknown", False, {"status": "unknown", "reason": f"unmapped outcome {label!r}"}, \
            {"from": repr(label), "to": "unknown"}
    if label in _OUTCOME_DETAIL_FIELD:
        return label, False, {"status": "known"}, None
    if label in PARTIAL_LABELS:
        return PARTIAL_LABELS[label], True, {"status": "known"}, {"from": label, "to": "fixed+partial"}
    if label in NOT_FIXED_LABELS:
        words = " ".join(str(disp.get(k) or "") for k in ("reason", "text")).lower()
        if not words.strip():
            return "unknown", False, {
                "status": "unknown", "reason": f"{label!r} carries no reason or text to read"}, \
                {"from": label, "to": "unknown"}
        to = "disputed" if any(m in words for m in DISPUTE_MARKERS) else "leftover"
        return to, False, {"status": "known"}, {"from": label, "to": to}
    return "unknown", False, {"status": "unknown", "reason": f"unmapped outcome {label!r}"}, \
        {"from": label, "to": "unknown"}


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
    """Set overlap/k on every finding; append each cross-reviewer match to `matches`.
    Findings group by (repo, ticket), because harvested rows carry no PR number.
    The verification pass is not a reviewer here (ruling 8, #1266): restating a
    round-1 finding leaves both unique, and a finding it raises new is unique."""
    by_ticket: dict[tuple, list[tuple[dict, dict]]] = {}
    for row in rows:
        for f in row["findings"]:
            if row["type"] == "verification":
                f["overlap"], f["k"] = "unique", 1
                continue
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


def _findings_name(name: str):
    """(axis, ticket group, round from the name) or None."""
    strict = parse_finding_sidecar_filename(name)
    if strict:
        return strict[0], str(strict[1]), 1
    m = _EXTRA_FINDINGS_RE.match(name)
    return (m.group(1), m.group(2), int(m.group(3) or 1)) if m else None


def _dispositions_group(name: str) -> str | None:
    n = parse_disposition_sidecar_filename(name)
    if n is not None:
        return str(n)
    m = _MULTI_DISPOSITIONS_RE.match(name)
    return m.group(1) if m else None


def harvest_cache(cache: Path, transcripts: Path | None, missing: str | None = None) -> tuple[list[dict], dict]:
    """(rows, review-file facts) for a whole cache tree. `transcripts` is the tree the
    Claude reviewers' cost is read from; None means there is none, for the reason `missing`."""
    pairs = find_sidecar_files(cache)  # FileNotFoundError when the cache is missing
    if not pairs:
        raise ValueError(f"no findings or dispositions sidecars under {cache}")
    by_repo: dict[str, list[str]] = {}
    for repo_dir, name in pairs:
        by_repo.setdefault(repo_dir, []).append(name)
    rows: list[dict] = []
    seen_ids: set[str] = set()
    mappings: Counter = Counter()
    unmapped: Counter = Counter()
    orphans: list[str] = []
    skipped: list[str] = []
    unharvested: list[str] = []
    for repo_dir in sorted(by_repo):
        repo = fold_repo(repo_dir)
        dispositions: dict[str, dict[str, dict]] = {}
        for name in sorted(by_repo[repo_dir]):
            if not name.startswith("dispositions-"):
                continue
            group = _dispositions_group(name)
            if group is None:
                unharvested.append(f"{repo_dir}/{name}")
                continue
            table: dict[str, dict] = {}
            for d in _read_sidecar(cache / repo_dir / name, skipped)[0]:
                if not isinstance(d.get("id"), str):
                    skipped.append(f"{repo_dir}/{name}: disposition without a string id")
                elif d["id"] in table:
                    skipped.append(f"{repo_dir}/{name}: duplicate disposition id {d['id']} (the later line wins)")
                    table[d["id"]] = d
                else:
                    table[d["id"]] = d
            dispositions[group] = table
        joined: set[tuple[str, str]] = set()
        seen_finding_ids: set[tuple[str, str]] = set()
        for name in sorted(by_repo[repo_dir]):
            if not name.startswith("findings-"):
                continue
            parsed = _findings_name(name)
            if parsed is None:
                unharvested.append(f"{repo_dir}/{name}")
                continue
            axis, group, name_round = parsed
            tickets = [int(t) for t in group.split("-")]
            if axis == "verify":
                mappings["verify -> verification (axis in filename)"] += 1
            base = "verification" if axis in ("verify", "verification") else axis
            path = cache / repo_dir / name
            raw_findings, lost = _read_sidecar(path, skipped)
            by_type: dict[tuple[str, int], list] = {(base, name_round): []}
            file_dispositions = dispositions.get(group)
            row_mappings: dict[tuple[str, int], list] = {}
            for raw in raw_findings:
                if not all(isinstance(raw.get(k), str) and raw[k] for k in ("id", "severity", "file", "title")):
                    skipped.append(f"{repo_dir}/{name}: finding without id/severity/file/title")
                    lost += 1
                    continue
                if (group, raw["id"]) in seen_finding_ids:
                    skipped.append(f"{repo_dir}/{name}: duplicate finding id {raw['id']} for ticket {group} "
                                   "(both kept; they join the same disposition)")
                seen_finding_ids.add((group, raw["id"]))
                row_type = "over-engineering" if base == "standards" and _OE_ID_RE.match(raw["id"]) else base
                rm = _ROUND_ID_RE.match(raw["id"])
                key = (row_type, int(rm.group(1)) if rm else name_round)
                if file_dispositions is None:
                    outcome, partial, status, mapping = "unknown", False, {
                        "status": "unknown", "reason": f"no dispositions file for ticket {group}"}, None
                elif raw["id"] not in file_dispositions:
                    outcome, partial, status, mapping = "unknown", False, {
                        "status": "unknown", "reason": f"no disposition line for {raw['id']}"}, None
                else:
                    joined.add((group, raw["id"]))
                    outcome, partial, status, mapping = normalise_outcome(file_dispositions[raw["id"]])
                if mapping:
                    (unmapped if mapping["to"] == "unknown" else mappings)[
                        f"{mapping['from']} -> {mapping['to']}"] += 1
                    row_mappings.setdefault(key, []).append(mapping)
                by_type.setdefault(key, []).append({
                    "id": raw["id"], "severity": raw["severity"], "severity_status": {"status": "known"},
                    "outcome": outcome, "outcome_status": status, "partial": partial,
                    "file": raw["file"], "title": raw["title"]})
            # A file named for round 1 whose every id says round 2 holds no round-1 run.
            base_key = (base, name_round)
            if not by_type[base_key] and len(by_type) > 1 and all(rnd != name_round for _, rnd in by_type if _ != base or rnd != name_round):
                del by_type[base_key]
            if lost:
                findings_status = {"status": "unknown", "reason": f"{lost} unreadable line(s) in the sidecar"}
            elif not raw_findings:
                findings_status = {"status": "unknown",
                                   "reason": "sidecar is empty: nothing found, or nothing written"}
            else:
                findings_status = {"status": "known"}
            for (row_type, rnd), findings in by_type.items():
                run_id = path.stem
                row_id = f"{repo}/{tickets[0]}/{row_type}/{rnd}/{run_id}"
                if row_id in seen_ids:
                    run_id = f"{repo_dir}:{run_id}"
                    row_id = f"{repo}/{tickets[0]}/{row_type}/{rnd}/{run_id}"
                seen_ids.add(row_id)
                sources = [f"{repo_dir}/{name}"]
                if file_dispositions is not None:
                    sources.append(f"{repo_dir}/dispositions-{group}.jsonl")
                rows.append({
                    "row_id": row_id, "origin": "harvest", "repo": repo, "pr": None, "ticket": tickets[0],
                    "tickets": tickets, "type": row_type, "round": rnd, "run_id": run_id, "model": None,
                    "findings": findings, "cost": None,
                    "status": {
                        "fields": {"pr": {"status": "unknown", "reason": "not in the sidecars"},
                                   "model": {"status": "unknown", "reason": "not in the sidecars"},
                                   "findings": findings_status},
                        "sources": sources, "mappings": row_mappings.get((row_type, rnd), [])}})
        for group, table in sorted(dispositions.items()):
            for fid in sorted(table):
                if (group, fid) not in joined:
                    orphans.append(f"{repo_dir} #{group} `{fid}` ({table[fid].get('outcome')})")
    runs, unattributed, ignored = read_transcripts(transcripts) if transcripts else ([], [], 0)
    rows += attach_costs(rows, runs, missing)
    rows.sort(key=lambda r: r["row_id"])
    matches: list[dict] = []
    mark_overlap(rows, matches)
    return rows, {"unattributed": sorted(unattributed), "ignored": ignored,
                  "mappings": mappings, "unmapped": unmapped, "matches": matches,
                  "orphans": sorted(set(orphans)), "skipped": sorted(set(skipped)),
                  "unharvested": sorted(unharvested)}


def review_file_text(facts: dict) -> str:
    def table(counter):
        return "\n".join(f"- `{k.split(' -> ')[0]}` -> {k.split(' -> ', 1)[1]}: {n}"
                         for k, n in sorted(counter.items())) or "- none"

    def bullets(items):
        return "\n".join(f"- {i}" for i in items) or "- none"

    matches = "\n".join(
        f"- {m['repo']} #{m['ticket']} `{m['file']}`: {m['a'][0]} {m['a'][1]} \"{m['a'][2]}\""
        f" = {m['b'][0]} {m['b'][1]} \"{m['b'][2]}\""
        for m in sorted(facts["matches"], key=lambda m: (m["repo"], m["ticket"], m["a"], m["b"]))) or "- none"
    return "\n".join([
        "# Review ledger harvest: review file", "",
        "## Label mappings applied", table(facts["mappings"]), "",
        "## Unmapped values", table(facts["unmapped"]), "",
        f"## Overlap matches ({len(facts['matches'])})",
        f"Rule: same file, and the word sets of the two normalised titles overlap by at least "
        f"{TITLE_MATCH_JACCARD} (Jaccard); matches chain transitively; findings group by ticket.",
        matches, "",
        "## Dispositions with no finding", bullets(facts["orphans"]), "",
        "## Sidecars not harvested (file name off the harvested patterns)", bullets(facts["unharvested"]), "",
        "## Skipped lines and duplicates", bullets(facts["skipped"]), "",
        "## Transcripts not attributed",
        f"{facts['ignored']} transcript(s) of other agent types were out of scope and are not listed.",
        bullets(facts["unattributed"]), ""])


def read_ledger(path: Path) -> list[dict]:
    """Every row of a ledger; a line that is not a JSON object fails loud, since
    the ledger also holds rows no harvest can rebuild."""
    rows = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{n}: not valid JSON ({e})") from e
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{n}: not a JSON object")
        rows.append(row)
    return rows


def cmd_harvest(args) -> int:
    try:
        transcripts, missing = args.transcripts, None
        if transcripts is None:
            transcripts = DEFAULT_TRANSCRIPTS
            if not transcripts.is_dir():
                transcripts, missing = None, f"transcripts tree not found: {DEFAULT_TRANSCRIPTS}"
        elif not transcripts.is_dir():
            raise FileNotFoundError(f"transcripts tree not found: {transcripts}")
        rows, facts = harvest_cache(args.cache, transcripts, missing)
        kept = [r for r in read_ledger(args.ledger) if r.get("origin") != "harvest"] \
            if args.ledger.exists() else []
    except (FileNotFoundError, ValueError) as e:
        print(f"review_ledger: {e}", file=sys.stderr)
        return 2
    everything = {r["row_id"]: r for r in kept}
    everything.update({r["row_id"]: r for r in rows})
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.write_text("".join(json.dumps(everything[k], sort_keys=True) + "\n" for k in sorted(everything)))
    review = args.review_file or args.ledger.with_suffix(".review.md")
    review.write_text(review_file_text(facts))
    print(f"harvested {len(rows)} rows into {args.ledger}; {sum(facts['unmapped'].values())} unmapped values, "
          f"{len(facts['matches'])} overlap matches, {len(facts['unharvested'])} sidecars not harvested, "
          f"{len(facts['skipped'])} skipped lines or duplicates, "
          f"{len(facts['unattributed'])} transcripts not attributed, listed in {review}")
    return 0


def summarise(rows: list[dict], weights: dict, split: str) -> dict:
    types = []
    present = {r["type"] for r in rows}
    for t in [*(t for t in REVIEW_TYPES if t in present), *sorted(present - set(REVIEW_TYPES))]:
        mine = [r for r in rows if r["type"] == t]
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
            "unknown_finding_rows": sum(r["status"]["fields"]["findings"]["status"] != "known" for r in mine),
            "unknown_cost_rows": sum(
                any(v.get("status") == "unknown" for v in r["cost"].values()) for r in mine)})
    notes = []
    if not present & set(MUTATION_TYPES):
        notes.append(f"No mutation rows: harvest writes none ({', '.join(MUTATION_TYPES)}); nothing on disk "
                     "records them in a form a script can read.")
    return {"types": types, "notes": notes}


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def cmd_report(args) -> int:
    try:
        rows = read_ledger(args.ledger)
    except (FileNotFoundError, ValueError) as e:
        print(f"review_ledger: {e}", file=sys.stderr)
        return 2
    weights = json.loads(args.weights.read_text()) if args.weights else DEFAULT_WEIGHTS
    result = summarise(rows, weights, args.split)
    if args.format == "json":
        print(json.dumps(result, indent=2))
        return 0
    print("| type | rows | findings | value | unique share | leftover rate | dispute rate "
          "| unknown outcomes | unweighted | unknown-findings rows | unknown-cost rows |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for t in result["types"]:
        print(f"| {t['type']} | {t['rows']} | {t['findings']} | {t['value']:.2f} | {_pct(t['unique_share'])} "
              f"| {_pct(t['leftover_rate'])} | {_pct(t['dispute_rate'])} | {t['unknown_outcomes']} "
              f"| {t['unweighted']} | {t['unknown_finding_rows']} | {t['unknown_cost_rows']} |")
    print()
    for note in result["notes"]:
        print(note)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("--cache", type=Path, default=REVIEWS_ROOT)
    h.add_argument("--transcripts", type=Path, help=f"default {DEFAULT_TRANSCRIPTS}")
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
