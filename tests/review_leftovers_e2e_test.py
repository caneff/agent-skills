#!/usr/bin/env python3
"""End-to-end test for spec #1024 (review leftovers: fix small findings
in-round, one sweep ticket per burn), closing ticket #1096.

One burn, driven through every command the spec's slices built, in the order
a controller and its workers run them, each command's output handed to the
next reader rather than a fixture standing in for it:

  1. `loop.py dispatch` over three candidates of closure sizes 1, 4 and 2
     with two free slots names the size-4 clump first (#1026).
  2. `runfile.py start` / `clump` register the two picked clumps.
  3. Each clump's verification pass writes a dispositions sidecar in
     `implement/SKILL.md` § Review's grammar — clump #901's is the shared
     fixture `implement/fixtures/dispositions-sidecar.jsonl`, every one of
     its five outcomes present — and `check_adjacent.py` measures the
     adjacent fix: in budget passes, a fix touching a second file fails the
     pass by finding id (#1025).
  4. `runfile.py land` / `leftover` copy each PR's `leftover` lines into the
     run file; `show` prints them and they survive `resume` (#1029).
  5. `sweep.py counts` prints the report's three counts (#1030).
  6. `sweep.py render` prints the sweep ticket, grouped by file, every field
     present; given `/file-ticket`'s `## Blocked by` tail it carries exactly
     one declaration, and `frontier.py` reads it as unblocked (#1030).
  7. A per-PR sweep filed outside a burn folds into the run sweep by its file
     sections only, and the folded body still declares `## Blocked by` once;
     the whole-body append the fold rule forbids reads `AMBIGUOUS` (#1033).
  8. A run whose landings left nothing renders nothing to file (#1030).

Seam: `bash tests/all.sh`, which runs this file.

Blind to: anything a human reads rather than a test asserts — whether a
model follows a skill's prose, whether a present `SKILL.md` instruction is
also unambiguous, and the harness behaviours around them (a hook denying a
step, a worker spinning on no-op tool calls, a pane closing before a
question is answered, #925). So a green run here does not show that a
worker applies the adjacent-fix rule rather than filing, that a verifier
reads `CONFIRMED` off a correctness report, that a controller runs the
second or third Codex pass only when the rule says to, or that `/file-ticket`
is actually called with the rendered body — only that every command those
steps name does what the step relies on, and that each one's output is
what the next one reads. The wording of those rules is held by the
`*-wording.test.sh` suites in `implement/` and `multi-axis-code-review/`;
the rest is the closing ticket's two opens of the real thing.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "burndown"))
import frontier  # noqa: E402

LOOP = os.path.join(ROOT, "burndown", "loop.py")
RUNFILE = os.path.join(ROOT, "burndown", "runfile.py")
SWEEP = os.path.join(ROOT, "burndown", "sweep.py")
CHECK_ADJACENT = os.path.join(ROOT, "multi-axis-code-review", "check_adjacent.py")
SHARED_SIDECAR = os.path.join(ROOT, "implement", "fixtures", "dispositions-sidecar.jsonl")
BURNDOWN_SKILL = os.path.join(ROOT, "burndown", "SKILL.md")
FILE_TICKET_SKILL = os.path.join(ROOT, "file-ticket", "SKILL.md")

RUN = "burn-e2e-1024"
FIXTURES = []


def scratch(prefix):
    root = tempfile.mkdtemp(prefix=prefix)
    FIXTURES.append(root)
    return root


def clean_fixtures():
    left = []
    while FIXTURES:
        root = FIXTURES.pop()
        shutil.rmtree(root, ignore_errors=True)
        if os.path.exists(root):
            left.append(root)
    return left


def cli(script, *args, env=None):
    result = subprocess.run([sys.executable, script, *args], capture_output=True,
                            text=True, env=env, stdin=subprocess.DEVNULL)
    return result


def ok(result):
    assert result.returncode == 0, (result.args, result.stdout, result.stderr)
    return result.stdout


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo, files, message):
    for path, text in files.items():
        full = os.path.join(repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def numbered(n):
    return "".join(f"line {i}\n" for i in range(n))


def write_jsonl(path, objects):
    with open(path, "w") as fh:
        for obj in objects:
            fh.write(json.dumps(obj) + "\n")


def with_blocked_by(body):
    """The body `/file-ticket` files: the given text, then the `## Blocked
    by` tail its template appends. The tail is read out of the skill, so a
    change to the template reaches this test rather than a copy of it."""
    with open(FILE_TICKET_SKILL) as fh:
        skill = fh.read()
    tail = "## Blocked by\n\n- None — can start immediately."
    assert tail + "\nEOF" in skill, \
        "file-ticket's template body no longer closes on the tail this test appends"
    return body.rstrip("\n") + "\n\n" + tail + "\n"


def fold(per_pr_body):
    """The per-PR sweep's file sections, as `burndown/SKILL.md` § The sweep
    tells a controller to take them. The skill's jq filter is asserted
    present and applied here as the same split."""
    with open(BURNDOWN_SKILL) as fh:
        skill = fh.read()
    assert '.body | split("\\n## Blocked by")[0]' in skill, \
        "burndown's fold no longer stops the per-PR body before its Blocked by"
    return per_pr_body.split("\n## Blocked by")[0]


def on_the_frontier(number, body):
    issue = {"number": number, "title": f"Sweep: leftovers from burn {RUN}",
             "body": body, "labels": [{"name": "ready-for-agent"}]}
    buckets = frontier.classify([issue], lambda n: "closed")
    return {name: [e["number"] for e in entries] for name, entries in buckets.items()}


def test_a_burn_from_widest_first_dispatch_to_one_sweep_ticket():
    work = scratch("spec-1024-e2e-")
    env = dict(os.environ, BURNDOWN_CACHE_DIR=os.path.join(work, "runs"))
    reviews = os.path.join(work, "reviews")
    os.makedirs(reviews)

    # 1. Widest clump first (#1026): two free slots, closures of 1, 4 and 2.
    candidates = os.path.join(work, "candidates.json")
    live = os.path.join(work, "live.json")
    with open(candidates, "w") as fh:
        json.dump([
            {"tickets": [905], "closure": ["burndown/cost.py"]},
            {"tickets": [901, 902], "closure": ["burndown/loop.py", "burndown/frontier.py",
                                                "burndown/runfile.py", "burndown/sweep.py"]},
            {"tickets": [910], "closure": ["burndown/references/loop.md", "implement/SKILL.md"]},
        ], fh)
    with open(live, "w") as fh:
        json.dump([], fh)
    dispatched = [line for line in ok(cli(
        LOOP, "dispatch", "--candidates", candidates, "--in-flight", live,
        "--free", "2", "--processes", "4", "--committed-gb", "4")).splitlines()
        if line.startswith("dispatch")]
    assert dispatched == ["dispatch  #901  #901,#902", "dispatch  #910  #910"], dispatched

    # 2. The run file holds the two picked clumps.
    ok(cli(RUNFILE, "start", RUN, "--slots", "2", "--controller", "burn-e2e", env=env))
    ok(cli(RUNFILE, "clump", RUN, "--tickets", "901,902", "--workspace",
           "/w/implement-901", "--agent", "w901", env=env))
    ok(cli(RUNFILE, "clump", RUN, "--tickets", "910", "--workspace",
           "/w/implement-910", "--agent", "w910", env=env))

    # 3. Clump #901's branch: ticket work in burndown/loop.py, a ticket fix
    # (S1), an adjacent fix to the same file (C2), and — for the breach
    # case — a fix that also touches a second file.
    repo = scratch("spec-1024-e2e-repo-")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "fixture")
    commit(repo, {"burndown/loop.py": numbered(40), "burndown/cost.py": numbered(40)}, "base")
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, {"burndown/loop.py": numbered(40) + "ticket work\n"}, "ticket work")
    ticket_fix = commit(repo, {"burndown/loop.py": numbered(40) + "ticket work, fixed\n"}, "S1")
    adjacent = commit(repo, {"burndown/loop.py": numbered(38) + "tick2 renamed\n"
                             + "ticket work, fixed\n"}, "C2, adjacent")

    with open(SHARED_SIDECAR) as fh:
        shared = [json.loads(raw) for raw in fh if raw.strip()]
    outcomes = sorted({line["outcome"] for line in shared})
    assert outcomes == ["disputed", "filed", "fixed", "handed-back", "leftover"], outcomes
    def bound(shas):
        """The shared sidecar with each named finding's sha bound to a real commit."""
        return [dict(line, sha=shas[line["id"]]) if line["id"] in shas else line
                for line in shared]

    shas = {"S1": ticket_fix, "C2": adjacent}
    sidecar_901 = os.path.join(reviews, "dispositions-901.jsonl")
    write_jsonl(sidecar_901, bound(shas))
    measured = cli(CHECK_ADJACENT, "--repo", repo, "--base", base, sidecar_901)
    assert measured.returncode == 0, (measured.stdout, measured.stderr)
    assert measured.stdout == "C2: ok, 3 changed lines in burndown/loop.py\n", measured.stdout

    two_files = commit(repo, {"burndown/loop.py": numbered(37) + "tick2 renamed again\n"
                              + "ticket work, fixed\n", "burndown/cost.py": numbered(41)},
                       "C2 again, spilling into cost.py")
    breach = os.path.join(work, "dispositions-901-breach.jsonl")
    write_jsonl(breach, bound(dict(shas, C2=two_files)))
    failed = cli(CHECK_ADJACENT, "--repo", repo, "--base", base, breach)
    assert failed.returncode == 1, (failed.stdout, failed.stderr)
    assert "BREACH C2: touches 2 files; the rule allows one" in failed.stdout, failed.stdout

    # Clump #910's verification pass: two leftovers — one in a file #901's
    # also named, so the sweep groups across clumps — and one fixed finding.
    sidecar_910 = os.path.join(reviews, "dispositions-910.jsonl")
    write_jsonl(sidecar_910, [
        {"id": "P1", "outcome": "leftover", "file": "burndown/loop.py",
         "title": "Dispatch line omits the closure size", "severity": "PLAUSIBLE",
         "text": "A controller reading `dispatch  #901` cannot see why it went first; ask @someone."},
        {"id": "C1", "outcome": "fixed", "sha": ticket_fix},
        {"id": "S1", "outcome": "leftover", "file": "implement/SKILL.md",
         "title": "Severity mapping sits under a <br> tag", "severity": "hard",
         "text": "The mapping renders on one line with the rule above it."},
    ])

    # 4. Landing copies each PR's leftovers into the run file (#1029).
    ok(cli(RUNFILE, "land", RUN, "--clump", "901", "--sha", "a1b2c3d", env=env))
    ok(cli(RUNFILE, "leftover", RUN, "--clump", "901", "--pr", "950", "--from",
           sidecar_901, env=env))
    ok(cli(RUNFILE, "land", RUN, "--clump", "910", "--sha", "d4e5f6a", env=env))
    ok(cli(RUNFILE, "leftover", RUN, "--clump", "910", "--pr", "951", "--from",
           sidecar_910, env=env))
    # A second copy of the same PR is a no-op, not a duplicate.
    ok(cli(RUNFILE, "leftover", RUN, "--clump", "910", "--pr", "951", "--from",
           sidecar_910, env=env))
    ok(cli(RUNFILE, "resume", RUN, "--live", "", env=env))
    shown = [line for line in ok(cli(RUNFILE, "show", RUN, env=env)).splitlines()
             if line.startswith("leftover")]
    assert shown == [
        "leftover  clump #901  #901,#902  PR #950  S3  judgement  burndown/loop.py  "
        "'Mysterious name: `tick2`'",
        "leftover  clump #910  #910  PR #951  P1  PLAUSIBLE  burndown/loop.py  "
        "'Dispatch line omits the closure size'",
        "leftover  clump #910  #910  PR #951  S1  hard  implement/SKILL.md  "
        "'Severity mapping sits under a <br> tag'",
    ], shown

    # 5. The report's three counts, read off the same sidecars (#1030):
    # fixed S1, C2 (adjacent), C1; leftover S3, P1, S1; standalone C1 (filed).
    counts = ok(cli(SWEEP, "counts", RUN, "--reviews-dir", reviews, env=env))
    assert counts == "fixed in-round: 3 (1 adjacent)  leftover: 3  standalone: 1\n", counts

    # 6. The sweep ticket (#1030): its title, then its body grouped by file in
    # first-seen order, every field a sweep worker needs, mentions and HTML
    # defused.
    rendered = cli(SWEEP, "render", RUN, env=env)
    title, blank, body = ok(rendered).split("\n", 2)
    assert (title, blank) == (f"Sweep: leftovers from burn {RUN}", ""), rendered.stdout
    assert body == (
        "## burndown/loop.py\n"
        "\n"
        "- **S3** (judgement) Mysterious name: `tick2` — clump #901, #901, #902, PR #950: "
        "tick2 says nothing about what it does; rename it for the frontier read it performs.\n"
        "- **P1** (PLAUSIBLE) Dispatch line omits the closure size — clump #910, #910, PR #951: "
        "A controller reading `dispatch  #901` cannot see why it went first; ask @​someone.\n"
        "\n"
        "## implement/SKILL.md\n"
        "\n"
        "- **S1** (hard) Severity mapping sits under a &lt;br> tag — clump #910, #910, PR #951: "
        "The mapping renders on one line with the rule above it.\n"
    ), body
    run_sweep = with_blocked_by(body)
    assert frontier.blocked_by_section(run_sweep) == "- None — can start immediately."
    assert on_the_frontier(1200, run_sweep)["unblocked"] == [1200]

    # 7. A per-PR sweep a worker outside the burn filed (#1033), in the same
    # shape, folds in by its file sections alone.
    per_pr = with_blocked_by(
        "## burndown/cost.py\n\n"
        "- **S2** (judgement) Magic 28 — PR #960: name the process cap.\n")
    folded = with_blocked_by(body.rstrip("\n") + "\n\n" + fold(per_pr))
    assert folded.count("## Blocked by") == 1, folded
    assert "- **S2** (judgement) Magic 28 — PR #960" in folded, folded
    assert on_the_frontier(1200, folded)["unblocked"] == [1200]
    whole = with_blocked_by(body.rstrip("\n") + "\n\n" + per_pr)
    assert frontier.blocked_by_section(whole) is frontier.AMBIGUOUS
    assert on_the_frontier(1200, whole)["unresolved"] == [1200]

    # 8. A run whose landings left nothing files nothing (#1030).
    quiet = "burn-e2e-1024-quiet"
    ok(cli(RUNFILE, "start", quiet, env=env))
    ok(cli(RUNFILE, "clump", quiet, "--tickets", "920", "--workspace", "/w/implement-920",
           "--agent", "w920", env=env))
    ok(cli(RUNFILE, "land", quiet, "--clump", "920", "--sha", "0a1b2c3", env=env))
    sidecar_920 = os.path.join(reviews, "dispositions-920.jsonl")
    write_jsonl(sidecar_920, [{"id": "C1", "outcome": "fixed", "sha": ticket_fix}])
    ok(cli(RUNFILE, "leftover", quiet, "--clump", "920", "--pr", "970", "--from",
           sidecar_920, env=env))
    nothing = cli(SWEEP, "render", quiet, env=env)
    assert (nothing.returncode, nothing.stdout) == (0, ""), nothing
    assert "nothing to file" in nothing.stderr, nothing.stderr
    counts = ok(cli(SWEEP, "counts", quiet, "--reviews-dir", reviews, env=env))
    assert counts == "fixed in-round: 1 (0 adjacent)  leftover: 0  standalone: 0\n", counts


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    try:
        for test in tests:
            test()
            print(f"ok  {test.__name__}")
        print(f"{len(tests)} passed")
    finally:
        left = clean_fixtures()
        if left:
            print(f"fixtures left behind: {', '.join(left)}", file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
