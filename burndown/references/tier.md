# Tier tagging: the label a ticket's targets call for

A ticket's **tier** is read off its `documentation` label at dispatch —
present is light, absent is heavy (the **Tier** entry in
[`../../CONTEXT.md`](../../CONTEXT.md)). A docs-only ticket whose author forgot the
label therefore gets the full heavy process for a page of prose. The exploration pass already knows each
candidate's files before dispatch, so it **writes the missing label onto the
ticket**, and takes a `documentation` label its code targets contradict back
off (§ Stripping). Reading it is `burndown/tier.py` — `python3 burndown/tier.py
<owner/repo> <n>=<path>[,<path>]... [--dry-run]`, or `tag(repo, candidates)`
in process.

The label, not a flag. A `--tier` flag is invisible the moment dispatch
returns, and `merge-cleanup`, `/landed` and a resumed controller all read the
ticket rather than the run's memory. A docs-only ticket that never got a
label is a defect in the ticket, and it is fixed on the ticket.

## Evidence

From the spec run on #781: ticket `#371` was a research ticket — one new
`docs/research/*.md`, tagged docs-only by the exploration pass — and carried
no `documentation` label. `implement-dispatch` sent it heavy: TDD, a
three-axis review and a pull request for a prose doc. The exploration pass
knew the answer before dispatch and the lane ignored it.

## The seam

`labels_to_write(candidate) -> labels`, where a candidate is
`{"number": <n>, "files": [...], "labels": [...]}` — the ticket's number, the
files it targets, and the labels it carries **right now**, read from the
tracker at pass time rather than assumed. Four answers, and only the first
writes anything:

- Every target file is prose, and the ticket has no `documentation` label →
  `["documentation"]`.
- Every target file is prose, and the label is already there → nothing. This
  pass is idempotent; a tick that runs twice writes once.
- Any target file is not prose → nothing. A mixed diff is code
  (`flow/claude/WORKFLOW.md` § Gate 2).
- The candidate names no files → nothing. `all()` over an empty list is
  `True`, and that is the one reading of "every file is prose" that sends an
  unknown candidate down the light tier.

**It only ever raises the tier.** `tag` builds `--add-label` from
`labels_to_write` and `--remove-label` from `labels_to_strip` alone, so the
one label a run ever takes off a ticket is `documentation`, and only from a
candidate targeting code. A worker keeps its right to raise light to heavy;
nothing raises heavy to light, and nothing here lowers it either.

## Stripping: a label the targets contradict

`labels_to_strip(candidate)` returns `["documentation"]` for a candidate that
carries the label while a target is not prose, and the pass removes it with
`--remove-label documentation` (#1045: #969 targeted a `SKILL.md`, carried the
filer's label, went out light and landed on main unreviewed). An empty file
list strips nothing: unknown targets are not evidence the label is wrong.

The pass does the removal because it is the only reader holding the
clumper's file list (#1118). `implement-dispatch` strips too, but from the
ticket body's paths alone, read by extension: on a code path
(`flow/claude/WORKFLOW.md` § Gate 2: `.py/.ts/.js/.sh/.rs`, a `SKILL.md`,
`settings.json`) it dispatches heavy, drops `documentation` in the claim edit,
and says so in its report; an unreadable body dispatches heavy and keeps the
label. A body naming only prose, on a ticket whose candidate line names a
`SKILL.md` or an extensionless script, gets past dispatch's reading — so the
label has to be gone before dispatch reads it, and this pass runs before the
first dispatch. The old report-only `--strip` flag is retired; `--dry-run`
previews the strip under `would strip:`.

## What counts as prose

A whitelist: `.md`, `.markdown`, `.txt`, `.rst`. Everything else is treated
as code, including an extension nobody thought of.

The one Markdown file that is not prose is a skill's **`SKILL.md`**, at any
depth. Its body changes what every later session does, which is why
`flow/claude/WORKFLOW.md` § Gate 2, the rule this classifier answers to,
names it as code.

**Why a whitelist and not the code list.** The gate
(`flow/claude/WORKFLOW.md` § Gate 2) names the *code* extensions, and a
classifier built from that list labels every unlisted extension as
documentation. Light tier lands on the default branch with no PR
and no reviewer, so a wrong `documentation` label ships a code change
unreviewed. A wrong heavy tier costs one review nobody needed. The two errors
are not the same size, and the whitelist is the one that fails toward the
cheap one.

## Divergence from the gate, deliberate

`flow/claude/WORKFLOW.md` § Gate 2, the two lanes, counts as not-code
"research notes and the scripts under `docs/research/` that nothing imports
or runs". **This reader does not honour that carve-out**: a `.py` under
`docs/research/` is code here.

A path cannot tell you whether something is run. `tests/all.sh` discovers
suites by three rules over git-tracked files — `*.test.sh`, `*_test.py`, and
each `audit.py` implementing `--selfcheck` — and none of them excludes
`docs/research/`. A probe script committed there under a `*_test.py` name is
executed by the merge gate, which is exactly the thing "nothing imports or
runs" promised it was not. The layout cannot keep that promise, so this
reader does not rely on it.

The divergence is stated here rather than fixed in `WORKFLOW.md`: the gate's
wording is Chris's to rule on, and a reader being stricter than the gate
costs a review, while editing the gate to match a reader changes what every
session does.

## The run's opening report names every label written

`tag` accumulates into the caller's own lists, and `render(written,
stripped=stripped)` is what the run's opening report carries — one line per
ticket, with the labels that went onto it or came off it — and a pass that
wrote none says `labels written: none` and `labels stripped: none` in words.
A `--dry-run` reports the same decisions under `would write:` and `would
strip:`, because a preview that claims a write is worse than no
preview: the line is the run's record of what the tracker now carries. A report silent about labels reads the same
as a report from a pass that never ran, and the difference between those two
is a ticket dispatched at the wrong tier.

A tracker failure partway through the candidate list is the case that makes
the accumulator worth its awkwardness: the labels already written are **on
the tracker** and the next dispatch will read them, so the command prints the
partial report to stdout before it prints the failure to stderr and exits 1.
A report that named nothing because the run ended badly would be the run
lying by omission.

## Where it sits in the run

After the frontier and the clumping, before the first dispatch: the tier is
read at dispatch, so a label written after it is a label that came too late.
The candidate strings are the clumper's own grammar,
`<n>=<path>[,<path>]...`, parsed by `closure.parse_candidate` and not by a
second parser here.
