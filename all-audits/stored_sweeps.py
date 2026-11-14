"""The stored sweeps and their audit records (#1679, #1680, #1747).

A `multi` sweep is stored outside the pruned cache, under
`stored_sweeps_base()/<repo>/<sweep-id>/`, and files one audit record, a
GitHub issue, in the swept repo. This module owns that layout and every `gh`
call about it: who owns the repo, its triage label, filing the record,
posting its missing comments, reading its state, and pruning the sweeps whose
record is closed. The sweep driver calls it; it never spawns `claude`.
"""
import datetime as _dt
import glob
import json
import os
import re
import shutil
import sys

from procs import run

MULTI_DIR = "multi"  # under stored_sweeps_base(): one folder per sweep id, never a repo's
OWNER = "caneff"


def stored_sweeps_base():
    """Where finished sweeps live: outside the run-folder cache the driver prunes."""
    return os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "all-audits")


def repo_identity(repo):
    """(`owner/name` on GitHub, None) when `gh` reports `caneff` owns the repo,
    else (None, why it is refused). The GitHub name, never the checkout's
    directory, keys the stored sweeps, so two checkouts of one repo share
    them. Anything `gh` cannot answer is a refusal, never a pass."""
    if not os.path.isdir(repo):
        return None, "no such directory"
    r = run(["gh", "repo", "view", "--json", "owner,name"], cwd=repo)
    if r.returncode != 0:
        return None, f"owner check failed (gh exit {r.returncode})"
    try:
        reply = json.loads(r.stdout)
        owner, name = reply["owner"]["login"], reply["name"]
    except (ValueError, KeyError, TypeError):
        return None, "owner check failed (gh reply unreadable)"
    if owner != OWNER:
        return None, f"owner is {owner}, not {OWNER}"
    return f"{owner}/{name}", None


TRIAGE_ROLE = "needs-triage"


def triage_label(checkout):
    """The repo's label string for the `needs-triage` role: its
    docs/agents/triage-labels.md mapping, else the role's own name."""
    path = os.path.join(checkout, "docs", "agents", "triage-labels.md")
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8", errors="replace"):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] == TRIAGE_ROLE and cells[1]:
                return cells[1]
    return TRIAGE_ROLE


def label_refusal(repo, label):
    """None when `repo` has `label`, else why it is refused. A `gh` that cannot
    answer is a refusal, never a pass; no label is ever created."""
    r = run(["gh", "label", "list", "--limit", "1000", "--json", "name"], cwd=repo)
    if r.returncode != 0:
        return f"label check failed (gh exit {r.returncode})"
    try:
        names = {row["name"] for row in json.loads(r.stdout)}
    except (ValueError, KeyError, TypeError):
        return "label check failed (gh reply unreadable)"
    return None if label in names else f"label `{label}` is missing"


RECORD_FILE = "audit-record.json"


def repo_sweep_dirs(name="*", sweep_id="*"):
    """Every repo's stored sweep folder, sorted, `name` and `sweep_id` as glob
    patterns. The multi-repo index folder (`MULTI_DIR`, #1721) holds no repo's
    sweeps and is never one."""
    return [d for d in sorted(glob.glob(os.path.join(stored_sweeps_base(), name, sweep_id)))
            if os.path.isdir(d) and os.path.basename(os.path.dirname(d)) != MULTI_DIR]


def stored_records(name=None):
    """Each stored sweep holding an audit record, oldest first within a repo:
    (sweep dir, record) with `issue` an int, or (sweep dir, None) when the
    record cannot be read. `name` keeps one repo's."""
    for sweep in repo_sweep_dirs(name or "*"):
        path = os.path.join(sweep, RECORD_FILE)
        if not os.path.isfile(path):
            continue
        try:
            rec = json.load(open(path, encoding="utf-8"))
            rec["issue"], rec["url"] = int(rec["issue"]), str(rec["url"])
        except (OSError, ValueError, KeyError, TypeError):
            rec = None
        yield sweep, rec


def record_repo(sweep, rec):
    """The GitHub repo a record was filed in. A record written before it held
    `owner/name` falls back to its directory's name."""
    slug = str(rec.get("repo", ""))
    return slug if "/" in slug else f"{OWNER}/{os.path.basename(os.path.dirname(sweep))}"


def issue_state(number, slug):
    """("OPEN" or "CLOSED", "") from `gh`, or (None, why). An answer that is
    neither is never read as either."""
    r = run(["gh", "issue", "view", str(number), "--repo", slug, "--json", "state"])
    try:
        state = json.loads(r.stdout)["state"] if r.returncode == 0 else None
    except (ValueError, KeyError, TypeError):
        state = None
    if state in ("OPEN", "CLOSED"):
        return state, ""
    err = r.stderr.strip()
    return None, f"gh exit {r.returncode}, state {state!r}{': ' + err if err else ''}"


def earlier_record(name):
    """(url, None) when `name`'s newest audit record is still open on GitHub,
    ("", None) when there is none or it is closed, and (None, why) when that
    cannot be told: an unreadable record or an unanswered state is a refusal,
    never "closed" (#1681)."""
    records = list(stored_records(name))
    if not records:
        return "", None
    sweep, rec = records[-1]
    if rec is None:
        return None, f"earlier record check failed ({os.path.join(sweep, RECORD_FILE)} unreadable)"
    state, why = issue_state(rec["issue"], record_repo(sweep, rec))
    if state is None:
        return None, f"earlier record check failed (issue #{rec['issue']}: {why})"
    return (rec["url"] if state == "OPEN" else ""), None


def record_history(name):
    """Every audit record filed for `name`, one JSON line each. A dot-directory,
    so no `<repo>/<sweep-id>` glob ever reads it as a repo or a sweep."""
    return os.path.join(stored_sweeps_base(), ".records", name + ".jsonl")


def resume_unposted(name):
    """Post, in order, the comments `name`'s newest audit record is still
    missing, before anything reads that record. Returns None, or why it could
    not: the record stays incomplete and says so."""
    records = list(stored_records(name))
    if not records or records[-1][1] is None or not records[-1][1].get("unposted"):
        return None
    sweep, rec = records[-1]
    while rec["unposted"]:
        c = run(["gh", "issue", "comment", str(rec["issue"]), "--repo", record_repo(sweep, rec),
                  "--body-file", os.path.join(sweep, rec["unposted"][0])])
        if c.returncode != 0:
            return (f"audit record {rec['url']} still misses comments {', '.join(rec['unposted'])} "
                    f"(gh exit {c.returncode}): {c.stderr.strip()}")
        rec["unposted"].pop(0)
        write_json(os.path.join(sweep, RECORD_FILE), rec)
    print(f"{name}: posted the missing comments of {rec['url']}")
    return None


def latest_record_url(name):
    """The newest audit record ever filed for `name`, open or closed, or "":
    where a skipped-as-unchanged audit's findings went. Read from the repo's
    record history, which outlives the stored sweeps closing deletes."""
    path = record_history(name)
    urls = []
    for line in open(path, encoding="utf-8").read().splitlines() if os.path.isfile(path) else []:
        try:
            urls.append(str(json.loads(line)["url"]))
        except (ValueError, KeyError, TypeError):
            continue
    return urls[-1] if urls else ""


SPEC_LIST_LIMIT = 1000


def open_specs_of(sweep, rec):
    """(numbers of the open issues in the record's repo whose body carries a
    `Sweep run:` line naming this stored sweep, None), or (None, why). The
    specs the triage filed are found by that line (#1851), the one every spec
    carries (`harness/GRILLING.md`), not by parsing the record's closing
    comment. A listing that fails, is not a list of bodies, or fills the
    limit (so may hide an open spec) is a refusal, never "none open"."""
    r = run(["gh", "issue", "list", "--repo", record_repo(sweep, rec), "--state", "open",
             "--limit", str(SPEC_LIST_LIMIT), "--json", "number,body"])
    if r.returncode != 0:
        return None, f"open-spec lookup failed (gh exit {r.returncode}): {r.stderr.strip()}"
    try:
        issues = [(int(i["number"]), str(i["body"])) for i in json.loads(r.stdout)]
    except (ValueError, KeyError, TypeError):
        return None, "open-spec lookup failed (gh reply unreadable)"
    if len(issues) >= SPEC_LIST_LIMIT:
        return None, f"open-spec lookup may be incomplete ({SPEC_LIST_LIMIT} open issues listed)"
    named = re.compile(r"^[\s>*_-]*Sweep run:.*[/\\]%s[/\\]%s(?![\w-])" % (
        re.escape(os.path.basename(os.path.dirname(sweep))), re.escape(os.path.basename(sweep))), re.M)
    return [n for n, body in issues if named.search(body)], None


def prune_closed_sweeps(ttl_days):
    """Delete each stored sweep whose audit record is CLOSED on GitHub and
    whose filed specs are all closed too (#1682, #1851): the record closes
    when triage files the specs, and each spec cites the sweep as its
    evidence. One whose record is open, unreadable, whose state `gh` does not
    answer, or that an open spec still names (or whose spec lookup fails) is
    kept, and a failed lookup is printed, never read as closed. A stored
    sweep with no record at all (its issue was never filed) is deleted once it
    is older than `ttl_days`, so nothing grows without bound. A multi-repo
    index (#1721) is deleted once it is that old and no stored sweep carrying
    its sweep id is left for it to link."""
    for sweep, rec in stored_records():
        if rec is None:
            print(f"stored sweep {sweep}: kept ({RECORD_FILE} unreadable)", file=sys.stderr)
            continue
        state, why = issue_state(rec["issue"], record_repo(sweep, rec))
        if state == "CLOSED":
            specs, why = open_specs_of(sweep, rec)
            if specs is None:
                print(f"stored sweep {sweep}: kept (record #{rec['issue']} closed, {why})", file=sys.stderr)
            elif specs:
                print(f"stored sweep {sweep}: kept (record #{rec['issue']} closed, spec "
                      f"{', '.join('#%d' % n for n in specs)} still open)", file=sys.stderr)
            else:
                shutil.rmtree(sweep, ignore_errors=True)
        elif state is None:
            print(f"stored sweep {sweep}: kept (record #{rec['issue']}: {why})", file=sys.stderr)
    cutoff = _dt.datetime.now().timestamp() - ttl_days * 86400
    for sweep in repo_sweep_dirs():
        if not os.path.exists(os.path.join(sweep, RECORD_FILE)) and os.path.getmtime(sweep) < cutoff:
            print(f"stored sweep {sweep}: deleted (no audit record, older than {ttl_days} days)",
                  file=sys.stderr)
            shutil.rmtree(sweep, ignore_errors=True)
    for page_dir in glob.glob(os.path.join(stored_sweeps_base(), MULTI_DIR, "*")):
        if (os.path.isdir(page_dir) and os.path.getmtime(page_dir) < cutoff
                and not repo_sweep_dirs(sweep_id=os.path.basename(page_dir))):
            print(f"multi-repo index {page_dir}: deleted (no stored sweep left to link, older than "
                  f"{ttl_days} days)", file=sys.stderr)
            shutil.rmtree(page_dir, ignore_errors=True)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def file_audit_record(repo, stored, title, label, chunks, meta):
    """Open the issue with `chunks[0]` and add the rest as comments, in order.
    The chunks stay in the stored sweep, and the record file is written the
    moment the issue exists, naming every comment not yet posted, so a failure
    part-way loses nothing. Returns (url, None) or (url_or_"", why it failed)."""
    paths = []
    for i, text in enumerate(chunks):
        paths.append(os.path.join(stored, f"audit-record-{i}.md"))
        with open(paths[-1], "w", encoding="utf-8") as f:
            f.write(text)
    created = run(["gh", "issue", "create", "--title", title, "--label", label, "--body-file", paths[0]], cwd=repo)
    match = re.search(r"/issues/(\d+)", created.stdout)
    if created.returncode != 0 or not match:
        return "", (f"audit record not filed (gh exit {created.returncode}): "
                    f"{created.stderr.strip() or created.stdout.strip()}; its text is in {stored}")
    url, number = created.stdout.strip().splitlines()[-1], match.group(1)
    meta = {**meta, "issue": int(number), "url": url, "unposted": [os.path.basename(p) for p in paths[1:]]}
    record_path = os.path.join(stored, RECORD_FILE)
    write_json(record_path, meta)
    history = record_history(os.path.basename(os.path.dirname(stored)))
    os.makedirs(os.path.dirname(history), exist_ok=True)
    with open(history, "a", encoding="utf-8") as f:
        f.write(json.dumps({"sweep": os.path.basename(stored), "url": url}) + "\n")
    for path in paths[1:]:
        c = run(["gh", "issue", "comment", number, "--body-file", path], cwd=repo)
        if c.returncode != 0:
            return url, (f"audit record {url} is missing continuation comments {', '.join(meta['unposted'])} "
                         f"(gh exit {c.returncode}): {c.stderr.strip()}; their text is in {stored}")
        meta["unposted"].pop(0)
        write_json(record_path, meta)
    return url, None


def find_stored_sweep(issue, repo_name=None):
    """(stored sweep dir, record) for the sweep whose audit record is issue
    `issue`, else (None, why). Never a guess: no match, two matches (the same
    number in two repos) and an unreadable record are each a refusal."""
    pattern = os.path.join(stored_sweeps_base(), repo_name or "*", "*", RECORD_FILE)
    found = []
    for sweep, rec in stored_records(repo_name):
        if rec is None:
            return None, f"stored record {os.path.join(sweep, RECORD_FILE)} is unreadable"
        if rec["issue"] == issue:
            found.append((sweep, rec))
    if not found:
        return None, f"no stored sweep for audit record #{issue}: expected {pattern} with \"issue\": {issue}"
    if len(found) > 1:
        return None, (f"audit record #{issue} matches {len(found)} stored sweeps "
                      f"({', '.join(s for s, _ in found)}): name the repo after the issue number")
    return found[0], None
