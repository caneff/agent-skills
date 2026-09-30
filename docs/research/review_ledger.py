#!/usr/bin/env python3
"""Review ledger (#1262 slice 1, #1265): one JSONL row per review run, and a
per-review-type value table.

    review_ledger.py harvest [--cache DIR] [--transcripts DIR] [--ledger PATH] [--review-file PATH]
    review_ledger.py append  --repo R --ticket N --type standards|spec|correctness|verification
                             [--round K] [--cache DIR] [--transcripts DIR] [--ledger PATH]
    review_ledger.py append  --repo R --ticket N --type witness-mutation|call-site-mutation|worker-mutation
                             --mutation-id ID --seconds S (--status-file PATH | --outcome red|green|unknown)
                             [--round K] [--ledger PATH]
    review_ledger.py report  [--ledger PATH] [--weights FILE] [--prices FILE] [--split 1/k|none]
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

Cost (#1266) is read from the diff-reviewer subagent transcripts under
`--transcripts` (`<project>/<session>/subagents/agent-<id>.{jsonl,meta.json}`): the
project directory names the repo and the worktree's ticket, the description and first
message name the axis and round. Tokens by kind come from each message's `usage`
(a streamed message counts once), wall clock from the first and last timestamps. A row
with no attributable transcript, or a transcript with no `usage`, is `unknown` with the
reason, never zero; over-engineering's cost stays inside its standards row. A transcript
no row holds becomes a row with unknown findings; one that cannot be attributed is listed.
A verification pass never counts toward overlap. Severity weights, the overlap split and
the price table (`--prices`, dollars per million tokens by model) live in `report`, never
in the ledger, so changing any of them needs no reharvest. `report` sums cost over known
rows only, counts the rest, and divides value by dollars over rows whose cost and findings
are both known.

Mutation rows (#1270) come only from `append`, one per mutation id: the outcome (`red`, `green`
or `unknown`) and the mutation's wall clock, no findings and no tokens (a reviewer's tokens stay
with its correctness row). A witness-check status file is read as the recipe writes it: the words
`red`, `green`, `unknown`, or a raw exit status (0 green, 126 and 127 unknown, any other number
red); anything else is `unknown`, never red or green. `report` gives a mutation type its red rate
over the mutations whose outcome is known, and counts the `unknown` ones beside it.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tally_review_axes import (
    _OUTCOME_DETAIL_FIELD, ALL_AXES, REVIEWS_ROOT, find_sidecar_files, fold_repo, load_jsonl,
    parse_disposition_sidecar_filename, parse_finding_sidecar_filename)

DEFAULT_LEDGER = REVIEWS_ROOT / "ledger.jsonl"
DEFAULT_TRANSCRIPTS = Path.home() / ".claude" / "projects"
TOKEN_KINDS = ("input", "output", "cache_write", "cache_read")
_USAGE_FIELDS = {"input": "input_tokens", "output": "output_tokens",
                 "cache_write": "cache_creation_input_tokens", "cache_read": "cache_read_input_tokens"}

# Report order. Mutation rows come from `append` only, Codex rows from nowhere yet.
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
    r"^-home-[^-]+(?:-src-(?P<src>.+?)|--agents-(?P<agents>.+?))(?:--claude-worktrees-(?:implement-(?P<n>\d+)|(?P<other>.+)))?$")


def _axis_of(text: str) -> str | None:
    """The one review type a phrase names, or None when it names none or several."""
    low = text.lower()
    if "verif" in low:
        return "verification"
    found = [a for a in ALL_AXES if a in low]
    return found[0] if len(found) == 1 else None


def _first_text(obj: dict) -> str | None:
    content = obj["message"].get("content") if isinstance(obj.get("message"), dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return None


def read_transcript(path: Path) -> dict:
    """The first user message, model, token totals and wall clock of one transcript.
    A streamed message is written as several lines sharing an id, each with the usage so
    far, so each token kind takes its maximum per id. A cache kind a usage block leaves
    out counts as none (the API omits it when nothing was cached). Anything that could
    hide tokens or time leaves that field unknown, with the reason: an unreadable line, an
    assistant message with no readable usage, a timestamp that does not parse."""
    per_id: dict[str, dict] = {}
    stamps: list[tuple[datetime, str]] = []
    models: Counter = Counter()
    first, lost, no_usage, bad_stamps = None, 0, 0, 0
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
                when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                stamps.append((when if when.tzinfo else when.replace(tzinfo=timezone.utc), ts))
            except ValueError:
                bad_stamps += 1
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
        else:
            no_usage += 1
    why = ([f"{lost} unreadable line(s) in the transcript"] if lost else []) + (
        [f"{no_usage} assistant message(s) with no readable usage"] if no_usage and per_id else [])
    if not per_id and not lost:
        why = ["transcript has no usage block"]
    tokens = {"status": "unknown", "reason": "; ".join(why)} if why else \
        {"status": "known", **{k: sum(m[k] for m in per_id.values()) for k in TOKEN_KINDS}}
    if lost or bad_stamps or not stamps:
        wall = {"status": "unknown", "reason": (
            f"{lost} unreadable line(s) in the transcript" if lost else
            f"{bad_stamps} timestamp(s) do not parse" if bad_stamps else "transcript has no readable timestamp")}
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
    if pm.group("other"):
        return None, ("worktree is not implement-N: its repo cannot be told from the directory it sits under, "
                      "which may hold a checkout of another repo")
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
    if axis != "verification" and "worktrees/review-" in head[:800]:
        return None, "spec-level review of a review worktree, not of this ticket's PR"
    rm = re.search(r"round[ -]?(\d+)", desc.lower()) or re.search(r"id prefix:\s*r(\d+)-", head.lower()) \
        or re.search(r"round[ -]?(\d+)", head[:120].lower())
    return {"repo": repo, "ticket": ticket, "type": axis, "round": int(rm.group(1)) if rm else 1}, ""


def read_transcripts(root: Path, tickets: set[int] | None = None) -> tuple[list[dict], list[str], int]:
    """(attributed runs, unattributed with reasons, count of other agent types ignored).
    `tickets` keeps only runs of those tickets, and skips a worktree project directory
    named for another ticket without reading its transcripts."""
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
        pm = _PROJECT_RE.match(project)
        if tickets is not None and pm and pm.group("n") and int(pm.group("n")) not in tickets:
            continue
        path = meta_path.with_name(agent + ".jsonl")
        if not path.exists():
            unattributed.append(f"{label}: meta.json has no transcript beside it")
            continue
        try:
            read = read_transcript(path)
        except (OSError, UnicodeError) as e:
            unattributed.append(f"{label}: unreadable transcript ({e.strerror or e})")
            continue
        key, why = attribute(meta, project, read["first"])
        if key is None:
            unattributed.append(f"{label}: {why}")
            continue
        if tickets is not None and key["ticket"] not in tickets:
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


def _norm_repo(name: str) -> str:
    """Claude Code writes `_` and `.` in a path as `-`, so a project directory cannot tell them apart."""
    return re.sub(r"[_.]", "-", name)


def new_row(row_id, repo, tickets, row_type, rnd, run_id, findings, findings_status, sources, *,
            model=None, cost=None, mappings=()) -> dict:
    """A harvested ledger row: the one place its shape is written."""
    return {
        "row_id": row_id, "origin": "harvest", "repo": repo, "pr": None, "ticket": tickets[0],
        "tickets": tickets, "type": row_type, "round": rnd, "run_id": run_id, "model": model,
        "findings": findings, "cost": cost,
        "status": {
            "fields": {"pr": {"status": "unknown", "reason": "not in the sidecars or the transcripts"},
                       "model": {"status": "known"} if model else
                       {"status": "unknown", "reason": "not in the sidecars or the transcripts"},
                       "findings": findings_status},
            "sources": sources, "mappings": list(mappings)}}


def attach_costs(rows: list[dict], runs: list[dict], missing: str | None) -> tuple[list[dict], dict]:
    """Fill each row's cost from its transcripts; returns (rows for runs no sidecar row holds,
    {"multi": the rows that sum more than one transcript, "shared": the transcripts behind a shared key}). A verification run whose round differs from
    its sidecar's joins that row when the ticket has exactly one verification row. Two sidecar
    rows on one key cannot split a transcript between them, so both stay unknown. Over-engineering
    cost stays inside standards."""
    canon = {_norm_repo(r["repo"]): r["repo"] for r in rows}
    by_key: dict[tuple, list[dict]] = {}
    by_type: dict[tuple, list[dict]] = {}
    for r in rows:
        for t in r["tickets"]:
            by_key.setdefault((r["repo"], t, r["type"], r["round"]), []).append(r)
        by_type.setdefault((r["repo"], r["ticket"], r["type"]), []).append(r)
    joined: dict[str, list[dict]] = {}
    shared: dict[str, str] = {}
    shared_runs: dict[str, list[str]] = {}
    extra: list[dict] = []
    for run in runs:
        run["repo"] = canon.get(_norm_repo(run["repo"]), run["repo"])
        hits = by_key.get((run["repo"], run["ticket"], run["type"], run["round"]), [])
        if not hits and run["type"] == "verification":
            hits = by_type.get((run["repo"], run["ticket"], "verification"), [])
            hits = hits if len(hits) == 1 else []
        if len(hits) > 1:
            key = f"({run['repo']}, #{run['ticket']}, {run['type']}, round {run['round']})"
            shared_runs.setdefault(key, []).append(run["source"])
            for h in hits:
                shared[h["row_id"]] = (f"{len(hits)} sidecar rows share ({run['repo']}, #{run['ticket']}, "
                                       f"{run['type']}, round {run['round']}); a transcript cannot be split between them")
        elif hits:
            joined.setdefault(hits[0]["row_id"], []).append(run)
        else:
            extra.append(run)
    multi = []
    for r in rows:
        runs_here = joined.get(r["row_id"], [])
        if r["type"] == "over-engineering":
            r["cost"] = {"tokens": dict(_INSIDE_STANDARDS), "wall_clock": dict(_INSIDE_STANDARDS),
                         "usage_delta": dict(_NOT_APPLICABLE)}
        elif r["row_id"] in shared:
            r["cost"] = unknown_cost(shared[r["row_id"]])
        elif runs_here:
            r["cost"], r["model"] = _merge_cost(runs_here)
            if r["model"]:
                r["status"]["fields"]["model"] = {"status": "known"}
            r["status"]["sources"] += [run["source"] for run in runs_here]
            if len(runs_here) > 1:
                multi.append(f"{r['row_id']}: {len(runs_here)} transcripts summed")
        else:
            r["cost"] = unknown_cost(missing or "no transcript attributed to this row")
    new_rows = []
    for run in extra:
        cost, model = _merge_cost([run])
        new_rows.append(new_row(
            f"{run['repo']}/{run['ticket']}/{run['type']}/{run['round']}/{run['agent']}", run["repo"],
            [run["ticket"]], run["type"], run["round"], run["agent"], [],
            {"status": "unknown", "reason": "no findings sidecar for this run: nothing found, or nothing written"},
            [run["source"]], model=model, cost=cost))
    return new_rows, {"multi": multi, "shared": [f"{k}: {', '.join(v)}" for k, v in sorted(shared_runs.items())]}


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


def mark_overlap(rows: list[dict], matches: list[dict], restatements: list[dict]) -> None:
    """Set overlap/k on every finding; append each cross-reviewer match to `matches`.
    Findings group by (repo, ticket), because harvested rows carry no PR number.
    The verification pass is not a reviewer here (ruling 8, #1266): it never shares a
    round-1 finding's credit. A verification finding that matches a finding of another
    reviewer is a restatement (`overlap: restated`, no credit, listed in `restatements`)
    and leaves the round-1 finding unique; one it raises new is unique."""
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

        restated = set()
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (ri, fi), (rj, fj) = items[i], items[j]
                if _reviewer(ri["type"]) == _reviewer(rj["type"]) or not titles_match(fi, fj):
                    continue
                pair = {"repo": repo, "ticket": ticket, "file": fi["file"],
                        "a": (ri["type"], fi["id"], fi["title"]), "b": (rj["type"], fj["id"], fj["title"])}
                if "verification" in (ri["type"], rj["type"]):
                    restated.add(i if ri["type"] == "verification" else j)
                    restatements.append(pair)
                else:
                    parent[find(i)] = find(j)
                    matches.append(pair)
        clusters: dict[int, set] = {}
        for i, (row, _) in enumerate(items):
            if row["type"] != "verification":
                clusters.setdefault(find(i), set()).add(_reviewer(row["type"]))
        for i, (row, f) in enumerate(items):
            if row["type"] == "verification":
                f["overlap"], f["k"] = ("restated" if i in restated else "unique"), 1
            else:
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


def _name_tickets(name: str) -> list[int]:
    """The tickets a findings or dispositions file name covers; none when the name is off-pattern."""
    found = _findings_name(name)
    group = found[1] if found else _dispositions_group(name)
    return [int(t) for t in group.split("-")] if group else []


def harvest_cache(cache: Path, transcripts: Path | None, missing: str | None = None,
                  only: tuple[str, int] | None = None) -> tuple[list[dict], dict]:
    """(rows, review-file facts) for a whole cache tree. `transcripts` is the tree the
    Claude reviewers' cost is read from; None means there is none, for the reason `missing`.
    `only` is (repo, ticket): harvest just that ticket's sidecars and transcripts, which is
    what `append` does, so its rows are the ones a full harvest writes."""
    pairs = find_sidecar_files(cache)  # FileNotFoundError when the cache is missing
    if not pairs:
        raise ValueError(f"no findings or dispositions sidecars under {cache}")
    if only:  # a cache directory name is literal; only a transcript's project directory loses `_` and `.`
        pairs = [(d, n) for d, n in pairs if fold_repo(d) == fold_repo(only[0]) and only[1] in _name_tickets(n)]
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
                rows.append(new_row(
                    row_id, repo, tickets, row_type, rnd, run_id, findings, findings_status, sources,
                    mappings=row_mappings.get((row_type, rnd), [])))
        for group, table in sorted(dispositions.items()):
            for fid in sorted(table):
                if (group, fid) not in joined:
                    orphans.append(f"{repo_dir} #{group} `{fid}` ({table[fid].get('outcome')})")
    wanted = {t for r in rows for t in r["tickets"]} if only else None
    runs, unattributed, ignored = read_transcripts(transcripts, wanted) if transcripts else ([], [], 0)
    if only:  # a ticket number repeats across repos
        runs = [r for r in runs if _norm_repo(fold_repo(r["repo"])) == _norm_repo(fold_repo(only[0]))]
    new_rows, listed = attach_costs(rows, runs, missing)
    rows += new_rows
    rows.sort(key=lambda r: r["row_id"])
    matches: list[dict] = []
    restatements: list[dict] = []
    mark_overlap(rows, matches, restatements)
    return rows, {**listed, "restatements": restatements, "unattributed": sorted(unattributed), "ignored": ignored,
                  "mappings": mappings, "unmapped": unmapped, "matches": matches,
                  "orphans": sorted(set(orphans)), "skipped": sorted(set(skipped)),
                  "unharvested": sorted(unharvested)}


def review_file_text(facts: dict) -> str:
    def table(counter):
        return "\n".join(f"- `{k.split(' -> ')[0]}` -> {k.split(' -> ', 1)[1]}: {n}"
                         for k, n in sorted(counter.items())) or "- none"

    def bullets(items):
        return "\n".join(f"- {i}" for i in items) or "- none"

    def match_lines(found):
        return "\n".join(
            f"- {m['repo']} #{m['ticket']} `{m['file']}`: {m['a'][0]} {m['a'][1]} \"{m['a'][2]}\""
            f" = {m['b'][0]} {m['b'][1]} \"{m['b'][2]}\""
            for m in sorted(found, key=lambda m: (m["repo"], m["ticket"], m["a"], m["b"]))) or "- none"

    matches = match_lines(facts["matches"])
    return "\n".join([
        "# Review ledger harvest: review file", "",
        "## Label mappings applied", table(facts["mappings"]), "",
        "## Unmapped values", table(facts["unmapped"]), "",
        f"## Overlap matches ({len(facts['matches'])})",
        f"Rule: same file, and the word sets of the two normalised titles overlap by at least "
        f"{TITLE_MATCH_JACCARD} (Jaccard); matches chain transitively; findings group by ticket.",
        matches, "",
        f"## Verification restatements ({len(facts['restatements'])})",
        "A verification finding matching another reviewer's finding (same rule) is a restatement: it earns no "
        "credit and leaves that finding unique (ruling 8).",
        match_lines(facts["restatements"]), "",
        "## Dispositions with no finding", bullets(facts["orphans"]), "",
        "## Sidecars not harvested (file name off the harvested patterns)", bullets(facts["unharvested"]), "",
        "## Skipped lines and duplicates", bullets(facts["skipped"]), "",
        "## Rows with more than one transcript",
        "Summed. Two or more can be a retried reviewer, or a transcript joined to the wrong row.",
        bullets(facts["multi"]), "",
        "## Transcripts behind a key several sidecar rows share",
        "Not summed into any row: which sidecar row a transcript belongs to cannot be told.",
        bullets(facts["shared"]), "",
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


def update_ledger(path: Path, change) -> None:
    """The one writer of the ledger: `change` edits {row_id: row} in place, under a lock, and the
    result replaces the file whole. `harvest` and `append` both come through here because three
    reviewers finish together and a harvest can overlap them; two plain read-modify-writes lose a row.
    A ledger that is not valid JSON raises ValueError and is left as found."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = {r["row_id"]: r for r in read_ledger(path)} if path.exists() else {}
        change(rows)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text("".join(json.dumps(rows[k], sort_keys=True) + "\n" for k in sorted(rows)))
        os.replace(tmp, path)


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

        def replace_harvest_rows(ledger: dict) -> None:
            for k in [k for k, r in ledger.items() if r.get("origin") == "harvest"]:
                del ledger[k]
            ledger.update({r["row_id"]: r for r in rows})

        update_ledger(args.ledger, replace_harvest_rows)
    except (FileNotFoundError, ValueError) as e:
        print(f"review_ledger: {e}", file=sys.stderr)
        return 2
    review = args.review_file or args.ledger.with_suffix(".review.md")
    review.write_text(review_file_text(facts))
    print(f"harvested {len(rows)} rows into {args.ledger}; {sum(facts['unmapped'].values())} unmapped values, "
          f"{len(facts['matches'])} overlap matches, {len(facts['unharvested'])} sidecars not harvested, "
          f"{len(facts['skipped'])} skipped lines or duplicates, "
          f"{len(facts['unattributed'])} transcripts not attributed, listed in {review}")
    return 0


APPEND_TYPES = ("standards", "spec", "correctness", "verification")
REVIEWER_TYPES = APPEND_TYPES + ("over-engineering",)
MUTATION_OUTCOMES = ("red", "green", "unknown")
_MUTATION_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _refusal(row: dict) -> str | None:
    """Why a row cannot be appended: the cost source it was read from is missing or unreadable."""
    for field in ("tokens", "wall_clock"):
        c = row["cost"][field]
        if c["status"] == "unknown":
            return f"cost source missing ({field}): {c['reason']}"
    return None


def decode_status(text: str) -> str:
    """A witness-check status file's outcome. The words, or the raw exit status the recipe
    records (its own case: 0 still passed, 126/127 never executed, other numbers failed);
    an empty or malformed file is `unknown`, never a pass or a red."""
    word = text.strip()
    if word in MUTATION_OUTCOMES:
        return word
    if re.fullmatch(r"\d+", word):
        code = int(word)
        return "green" if code == 0 else "unknown" if code in (126, 127) else "red"
    return "unknown"


def cmd_append_mutation(args) -> int:
    """Write the one row of a mutation that just ran. Its outcome comes from a status file or
    `--outcome`, its wall clock from `--seconds`; there is no cache or transcript to read."""
    try:
        if args.cache is not None or args.transcripts is not None:
            raise ValueError("--cache and --transcripts are for review types, not mutation rows")
        if not args.mutation_id or not _MUTATION_ID_RE.match(args.mutation_id):
            raise ValueError("a mutation row needs --mutation-id made of letters, digits, . - _")
        if (args.status_file is None) == (args.outcome is None):
            raise ValueError("give exactly one of --status-file and --outcome")
        try:
            seconds = float(args.seconds)
        except (TypeError, ValueError):
            seconds = None
        if seconds is None or not 0 <= seconds < float("inf"):
            raise ValueError("a mutation row needs --seconds, its wall clock as a finite number of seconds")
        outcome = args.outcome or decode_status(args.status_file.read_text())
    except (OSError, ValueError) as e:
        print(f"review_ledger append: {e}", file=sys.stderr)
        return 2
    seconds = int(seconds) if seconds == int(seconds) else seconds
    repo = fold_repo(args.repo)
    row_id = f"{repo}/{args.ticket}/{args.type}/{args.round}/{args.mutation_id}"
    row = new_row(row_id, repo, [args.ticket], args.type, args.round,
                  args.mutation_id, [], {"status": "not-applicable", "reason": "a mutation row holds no findings"},
                  [], cost={"tokens": {"status": "not-applicable",
                                       "reason": "a reviewer's tokens stay with its correctness row"},
                            "wall_clock": {"status": "known", "seconds": seconds}})
    row.update(origin="append", mutation_id=args.mutation_id, outcome=outcome)
    try:
        update_ledger(args.ledger, lambda ledger: ledger.update({row_id: row}))
    except ValueError as e:
        print(f"review_ledger append: {e}", file=sys.stderr)
        return 2
    print(f"appended 1 row to {args.ledger}: {row_id} ({outcome})")
    return 0


def cmd_append(args) -> int:
    """Write the rows of one review that just ran: what `harvest` would write for that
    ticket's sidecars and transcripts, selected by type and round. A review's own cost or
    findings sidecar being absent is a refusal, never a row with zero cost. A round-1 review
    ends before its dispositions exist, so its findings' outcomes are `unknown` until the
    same append is run again after them, or a harvest reads them."""
    if args.type in MUTATION_TYPES:
        return cmd_append_mutation(args)
    if args.mutation_id or args.status_file or args.outcome or args.seconds is not None:
        print(f"review_ledger append: --mutation-id, --status-file, --outcome and --seconds are for "
              f"mutation types, not {args.type}", file=sys.stderr)
        return 2
    args.cache = args.cache or REVIEWS_ROOT
    try:
        transcripts = args.transcripts or DEFAULT_TRANSCRIPTS
        if not transcripts.is_dir():
            raise FileNotFoundError(f"transcripts tree not found: {transcripts}")
        rows, _ = harvest_cache(args.cache, transcripts, only=(args.repo, args.ticket))
    except (FileNotFoundError, ValueError) as e:
        print(f"review_ledger append: {e}", file=sys.stderr)
        return 2
    want = {args.type} | ({"over-engineering"} if args.type == "standards" else set())
    mine = [r for r in rows if r["type"] in want and r["round"] == args.round]
    if not any(r["type"] == args.type and any(Path(x).name.startswith("findings-") for x in r["status"]["sources"])
               for r in mine):
        print(f"review_ledger append: no findings sidecar for {args.type} round {args.round} of "
              f"{args.repo} #{args.ticket} under {args.cache}", file=sys.stderr)
        return 2
    for r in mine:
        if (why := _refusal(r)):
            print(f"review_ledger append: {r['row_id']}: {why}", file=sys.stderr)
            return 2
    ticket = (mine[0]["repo"], mine[0]["ticket"])

    def add_rows(ledger: dict) -> None:
        ledger.update({r["row_id"]: {**r, "origin": "append"} for r in mine})
        # The ticket's other reviewers may have appended already: re-split credit across all of them.
        # Only rows of reviewer types: a row another writer adds (codex, mutation) is not ours to re-score.
        mark_overlap([r for r in ledger.values() if (r.get("repo"), r.get("ticket")) == ticket
                      and r.get("type") in REVIEWER_TYPES], [], [])

    try:
        update_ledger(args.ledger, add_rows)
    except ValueError as e:
        print(f"review_ledger append: {e}", file=sys.stderr)
        return 2
    print(f"appended {len(mine)} row(s) to {args.ledger}: {', '.join(r['row_id'] for r in mine)}")
    return 0


def _row_value(row: dict, weights: dict, split: str) -> tuple[float, int]:
    """(weighted value, findings whose severity has no weight) of one row."""
    value, unweighted = 0.0, 0
    for f in row["findings"]:
        if f["outcome"] not in VALUE_OUTCOMES or f["overlap"] == "restated":
            continue
        weight = weights.get(f["severity"])
        if weight is None:
            unweighted += 1
            continue
        value += weight / (f["k"] if split == "1/k" else 1)
    return value, unweighted


def _row_dollars(row: dict, prices: dict | None) -> float | None:
    """Dollars of one row from its token kinds and its model's price per million tokens, or
    None when the tokens are unknown or the model has no price."""
    tokens = row["cost"].get("tokens", {})
    price = (prices or {}).get(row.get("model"))
    if tokens.get("status") != "known" or not isinstance(price, dict) \
            or not all(isinstance(price.get(k), (int, float)) for k in TOKEN_KINDS):
        return None
    return sum(tokens[k] * price[k] for k in TOKEN_KINDS) / 1_000_000


def summarise(rows: list[dict], weights: dict, split: str, prices: dict | None = None) -> dict:
    types = []
    oe_value: dict[tuple, float] = {}
    for r in rows:
        if r["type"] == "over-engineering":
            key = (r["repo"], r["ticket"], r["round"])
            oe_value[key] = oe_value.get(key, 0.0) + _row_value(r, weights, split)[0]
    present = {r["type"] for r in rows}
    for t in [*(t for t in REVIEW_TYPES if t in present), *sorted(present - set(REVIEW_TYPES))]:
        mine = [r for r in rows if r["type"] == t]
        findings = [f for r in mine for f in r["findings"]]
        per_row = [(r, *_row_value(r, weights, split), _row_dollars(r, prices)) for r in mine]
        value, unweighted = sum(v for _, v, _, _ in per_row), sum(u for _, _, u, _ in per_row)
        known = [f for f in findings if f["outcome"] != "unknown"]
        rate = lambda outcome: (sum(f["outcome"] == outcome for f in known) / len(known)) if known else None
        inside = t == "over-engineering"
        mutation = t in MUTATION_TYPES
        outcomes = Counter(r.get("outcome") for r in mine) if mutation else Counter()
        red_known = outcomes["red"] + outcomes["green"]
        costs = [r["cost"] for r in mine]
        token_rows = [c["tokens"] for c in costs if c.get("tokens", {}).get("status") == "known"]
        wall_rows = [c["wall_clock"] for c in costs if c.get("wall_clock", {}).get("status") == "known"]
        priced = [(r, v, d) for r, v, _, d in per_row if d is not None]
        # Value per dollar divides only the value of rows whose cost and findings are both
        # known by those rows' dollars: an unknown row is left out, never counted as free.
        rated = []
        for r, v, d in priced:
            if r["status"]["fields"]["findings"]["status"] == "known":
                # Over-engineering cost is inside its standards row's dollars, so its value joins the numerator.
                extra = oe_value.pop((r["repo"], r["ticket"], r["round"]), 0.0) if t == "standards" else 0.0
                rated.append((v + extra, d))
        rated_dollars = sum(d for _, d in rated)
        types.append({
            "type": t, "rows": len(mine), "findings": len(findings), "value": round(value, 4),
            "unique_share": (sum(f["overlap"] == "unique" for f in findings) / len(findings)) if findings else None,
            "leftover_rate": rate("leftover"), "dispute_rate": rate("disputed"),
            "unknown_outcomes": len(findings) - len(known), "unweighted": unweighted,
            "unknown_finding_rows": 0 if mutation else sum(
                r["status"]["fields"]["findings"]["status"] != "known" for r in mine),
            "unknown_cost_rows": 0 if inside else sum(
                any(c.get(f, {}).get("status") not in ("known", "not-applicable") for f in ("tokens", "wall_clock"))
                for c in costs),
            # A mutation type's red rate leaves the `unknown` ones out, like the outcome rates above;
            # they are counted beside it. Only mutation rows carry either.
            "red_rate": outcomes["red"] / red_known if red_known else None,
            "unknown_mutations": len(mine) - red_known if mutation else None,
            "cost_note": "inside standards" if inside else None,
            "tokens": None if inside or not token_rows else {k: sum(c[k] for c in token_rows) for k in TOKEN_KINDS},
            "wall_clock_seconds": None if inside or not wall_rows else sum(c["seconds"] for c in wall_rows),
            "dollars": None if inside or not priced else round(sum(d for _, _, d in priced), 4),
            "unpriced_rows": 0 if inside else sum(
                1 for r, _, _, d in per_row if r["cost"].get("tokens", {}).get("status") == "known" and d is None),
            "value_per_dollar": round(sum(v for v, _ in rated) / rated_dollars, 4)
            if not inside and rated_dollars else None})
    notes = []
    notes.append("Reviews before #1270 carry no mutation data: a review run earlier has no mutation rows, "
                 "so a mutation type's counts start at that change and a missing type is n/a, not zero."
                 + ("" if present & set(MUTATION_TYPES) else " No mutation rows are in this ledger yet."))
    for t in types:
        if prices is not None and t["unpriced_rows"]:
            notes.append(f"{t['type']}: {t['unpriced_rows']} row(s) have tokens but no price for their model; "
                         "left out of dollars and value per dollar, not counted as free.")
    if prices is None:
        notes.append("No price table: dollars and value per dollar are n/a, not zero (pass --prices).")
    return {"types": types, "notes": notes}


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _cost_cells(t: dict) -> list[str]:
    if t["cost_note"]:
        return [t["cost_note"]] * 3 + ["n/a"]
    tokens = "n/a" if t["tokens"] is None else f"{sum(t['tokens'].values()):,}"
    wall = "n/a" if t["wall_clock_seconds"] is None else f"{t['wall_clock_seconds']:.0f}s"
    dollars = "n/a" if t["dollars"] is None else f"${t['dollars']:.2f}"
    vpd = "n/a" if t["value_per_dollar"] is None else f"{t['value_per_dollar']:.4f}"
    return [tokens, wall, dollars, vpd]


def cmd_report(args) -> int:
    try:
        rows = read_ledger(args.ledger)
        prices = json.loads(args.prices.read_text()) if args.prices else None
        if prices is not None and not isinstance(prices, dict):
            raise ValueError(f"{args.prices}: a price table is a JSON object of model -> prices")
    except (FileNotFoundError, ValueError) as e:
        print(f"review_ledger: {e}", file=sys.stderr)
        return 2
    weights = json.loads(args.weights.read_text()) if args.weights else DEFAULT_WEIGHTS
    result = summarise(rows, weights, args.split, prices)
    if args.format == "json":
        print(json.dumps(result, indent=2))
        return 0
    print("| type | rows | findings | value | unique share | leftover rate | dispute rate "
          "| unknown outcomes | unweighted | unknown-findings rows | unknown-cost rows "
          "| tokens | wall clock | dollars | value per dollar | red rate | unknown mutations |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in result["types"]:
        print(f"| {t['type']} | {t['rows']} | {t['findings']} | {t['value']:.2f} | {_pct(t['unique_share'])} "
              f"| {_pct(t['leftover_rate'])} | {_pct(t['dispute_rate'])} | {t['unknown_outcomes']} "
              f"| {t['unweighted']} | {t['unknown_finding_rows']} | {t['unknown_cost_rows']} "
              f"| {' | '.join(_cost_cells(t))} | {_pct(t['red_rate'])} "
              f"| {'n/a' if t['unknown_mutations'] is None else t['unknown_mutations']} |")
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
    a = sub.add_parser("append")
    a.add_argument("--repo", required=True, help="the review cache's repo directory name")
    a.add_argument("--ticket", type=int, required=True)
    a.add_argument("--type", choices=APPEND_TYPES + MUTATION_TYPES, required=True)
    a.add_argument("--round", type=int, default=1)
    a.add_argument("--cache", type=Path, default=None, help=f"default {REVIEWS_ROOT}")
    a.add_argument("--mutation-id", help="a mutation type: the id the mutation is reported by")
    a.add_argument("--status-file", type=Path, help="a mutation type: the witness check's status file for the id")
    a.add_argument("--outcome", choices=MUTATION_OUTCOMES, help="a mutation type: the outcome, when no status file")
    a.add_argument("--seconds", help="a mutation type: the mutation's wall clock")
    a.add_argument("--transcripts", type=Path, help=f"default {DEFAULT_TRANSCRIPTS}")
    a.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    a.set_defaults(func=cmd_append)
    r = sub.add_parser("report")
    r.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    r.add_argument("--weights", type=Path)
    r.add_argument("--prices", type=Path, help="JSON: model -> {input, output, cache_write, cache_read} "
                   "dollars per million tokens")
    r.add_argument("--split", choices=("1/k", "none"), default="1/k")
    r.add_argument("--format", choices=("md", "json"), default="md")
    r.set_defaults(func=cmd_report)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
