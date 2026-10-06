#!/usr/bin/env python3
"""render-brief.py (#1216, #1329, #1400): the one source of an axis reviewer's
brief. Seam: the CLI, run against a throwaway worktree directory. Each case
asserts the line it is about, so a render that fails for another reason (a
missing input, a bad path) does not pass for the one under test
(`AGENTS.md` § Recurring defect classes, class 3).
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "render-brief.py")
SHAPES = ("an absent or malformed answer read as a benign one",
          "a stated fallback with no mechanism behind it",
          "a test that passes for a reason other than the one it claims")
FAILS = []


def check(name, ok, detail=""):
    if ok:
        print(f"PASS: {name}")
    else:
        FAILS.append(f"FAIL: {name} {detail}")


def render(worktree, diff, *extra, axis="standards", explicit_spec=False):
    args = ["python3", RENDER, "--axis", axis, "--repo", "skills", "--worktree", worktree,
            "--ticket", "1395", "--base", "origin/main", "--diff", diff,
            "--diff-command", "git -C WT diff origin/main...HEAD", "--commit", "abc1234 first commit",
            *extra]
    if axis != "standards" and not {"--spec", "--no-spec"} & set(extra) and not explicit_spec:
        args.append("--no-spec")
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def section(out, heading):
    """The body of a `## heading` section, or None when there is no such heading."""
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", out, re.M | re.S)
    return m.group(1) if m else None


def main():
    with tempfile.TemporaryDirectory() as tmp:
        wt = os.path.join(tmp, "wt")
        os.makedirs(os.path.join(wt, "docs", "agents"))
        open(os.path.join(wt, "CODING_STANDARDS.md"), "w").write("x\n")
        diff = os.path.join(tmp, "diff.patch")
        open(diff, "w").write("diff --git a/f b/f\n" * 7)

        code, out, err = render(wt, diff)
        check("a minimal render succeeds", code == 0, err)
        check("the diff's line count is read from the file, not asserted",
              "(7 lines)" in out, out)
        check("the report filename is pinned once, for this axis and ticket",
              out.count("review-standards-1395.md") == 1 and "review-spec" not in out, out)
        check("the sidecar and marker names are pinned",
              "findings-standards-1395.jsonl" in out and "findings-standards-1395.done" in out, out)

        # #1329: standards sources are listed from the worktree with ls, not asserted.
        src = section(out, "Standards sources") or ""
        check("a standards file present in the worktree is listed", "CODING_STANDARDS.md" in src, src)
        check("a standards file absent from the worktree is not listed", "CONTRIBUTING.md" not in src, src)
        open(os.path.join(wt, "GLOSSARY.md"), "w").write("x\n")
        _, out_g, _ = render(wt, diff)
        src_g = section(out_g, "Standards sources") or ""
        check("the domain glossary present in the worktree is listed as GLOSSARY.md",
              "GLOSSARY.md" in src_g, src_g)
        os.remove(os.path.join(wt, "GLOSSARY.md"))
        dc = section(out, "Defect classes") or ""
        check("defect-classes.md absent: the three shapes are inline and the file is not named as a source",
              all(s in dc for s in SHAPES) and "defect-classes.md" not in src, dc)
        open(os.path.join(wt, "docs", "agents", "defect-classes.md"), "w").write("x\n")
        code, out2, _ = render(wt, diff)
        src2, dc2 = section(out2, "Standards sources") or "", section(out2, "Defect classes") or ""
        check("defect-classes.md present: listed as a source and read by name, shapes not retyped",
              "docs/agents/defect-classes.md" in src2 and "docs/agents/defect-classes.md" in dc2
              and not any(s in dc2 for s in SHAPES), (src2, dc2))

        # #1216/#1400: rulings, the worker's choices and claims stay in their own sections.
        code, out, err = render(wt, diff, "--ruling", "RULED-X by Chris", "--choice", "CHOSE-Y by worker",
                                "--claim", "S1: CLAIM-Z the worker says it fixed this")
        settled, own = section(out, "Settled decisions") or "", section(out, "Worker's own choices") or ""
        claims = section(out, "Claims to check") or ""
        check("a ruling is printed under Settled decisions only",
              "RULED-X" in settled and out.count("RULED-X") == 1, out)
        check("a worker's choice is never settled: own section, flagged, absent from Settled",
              "CHOSE-Y" in own and "flag" in own.lower() and "CHOSE-Y" not in settled, out)
        check("a claim is printed under the claims heading only, as a claim to check",
              "CLAIM-Z" in claims and out.count("CLAIM-Z") == 1 and "claim" in claims.lower()
              and "CLAIM-Z" not in settled, out)
        code, out, _ = render(wt, diff)
        check("no claims: no claims heading", section(out, "Claims to check") is None, out)
        check("no rulings: the list says none rather than vanishing",
              "settled decisions: none" in (section(out, "Settled decisions") or "").lower(), out)
        check("the renderer never emits an outcome of its own",
              not re.search(r'"outcome"|\b(fixed|moved|disputed)\b', out), out)
        code, out_c, _ = render(wt, diff, "--claim", "S1: it says fixed", axis="correctness")
        check("a claim's own words are the only place an outcome word appears",
              len(re.findall(r'\b(fixed|moved|disputed)\b', out_c)) == 1, out_c)

        # #1400: nested agents, worker count and ceiling.
        check("the brief forbids a nested subagent", "no nested subagent" in out.lower(), out)
        check("default worker count and wall-clock ceiling are stated",
              "at most 1 worker" in out and "600 seconds" in out, out)
        code, out, _ = render(wt, diff, "--workers", "3", "--ceiling", "90")
        check("worker count and ceiling are taken from the inputs",
              "at most 3 worker" in out and "90 seconds" in out, out)

        # #1230: the rating field belongs to the correctness sidecar.
        _, out_c, _ = render(wt, diff, axis="correctness")
        _, out_s, _ = render(wt, diff, axis="spec")
        check("the correctness sidecar schema carries rating CONFIRMED/PLAUSIBLE",
              '"rating": "CONFIRMED" or "PLAUSIBLE"' in out_c, out_c)
        check("the spec sidecar schema carries no rating", '"rating"' not in out_s, out_s)

        # Refusals name their cause and never render a half brief.
        code, out, err = render(wt, os.path.join(tmp, "nope.patch"))
        check("a missing diff capture is refused by name", code == 2 and "nope.patch" in err and not out, err)
        open(os.path.join(tmp, "empty.patch"), "w").close()
        code, out, err = render(wt, os.path.join(tmp, "empty.patch"))
        check("an empty diff capture is refused", code == 2 and "empty" in err and not out, err)
        code, out, err = render(os.path.join(tmp, "no-such-dir"), diff)
        check("a worktree that is not a directory is refused", code == 2 and "no-such-dir" in err, err)
        code, out, err = render(wt, diff, axis="docs")
        check("an unknown axis is refused", code == 2, err)
        code, out, err = render(wt, diff, axis="spec", explicit_spec=True)
        check("a spec axis with neither --spec nor --no-spec is refused, not read as 'no spec'",
              code == 2 and "--spec" in err and not out, err)
        code, out, err = render(wt, diff, "--spec", "x.md", "--no-spec", axis="correctness")
        check("--spec together with --no-spec is refused", code == 2 and "both" in err and not out, err)
        code, out, err = render(wt, diff, "--no-spec", axis="correctness")
        check("--no-spec renders 'no spec available'", code == 0 and "no spec available" in out, err)
        code, out, err = render(wt, diff, "--claim", "no colon here")
        check("a claim with no finding id is refused", code == 2 and "no colon here" in err, err)

        # #1218: the capture's stat line reaches the prompt.
        code, out, _ = render(wt, diff, "--capture-stat", "captured: 3 files; excluded 1 generated file(s): g/x.json")
        check("the capture's stat line is printed under Inputs",
              "captured: 3 files; excluded 1 generated file(s): g/x.json" in (section(out, "Inputs") or ""), out)
        # #1325/#1324: the worker cap binds the witness check, which has its own concurrency.
        _, out_c, _ = render(wt, diff, "--workers", "2", axis="correctness")
        _, out_s, _ = render(wt, diff, "--workers", "2")
        check("the correctness prompt tells the witness check its slot cap", "--slots 2" in out_c, out_c)
        check("a prompt with no witness check carries no --slots", "--slots" not in out_s, out_s)

        # Each axis renders its own brief, from the one file per axis.
        for axis, needle in (("standards", "Over-engineering"), ("spec", "scope creep"),
                             ("correctness", "witness-check.sh")):
            _, o, _ = render(wt, diff, axis=axis)
            check(f"the {axis} brief is included", needle in (section(o, "Brief") or ""), o)
    if FAILS:
        print("\n".join(FAILS))
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
