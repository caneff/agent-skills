# Weekly Codex audit

Once per Codex quota window, one Codex adversarial review covers every
merged PR that skipped its merge-gate pass for size or the reserve ceiling
(`SKILL.md` § The merge step 3). Confirmed findings become one
`ready-for-agent` ticket each. The controller running it owns every step
below; no worker is involved, and nothing is posted to the merged PRs.

Run it by hand near the end of the window: the reserve above 70 % exists
for this run, and it is spent only when the window is about to reset. The
reset time is the one the usage gate prints.

## 1. Run

From the primary checkout of the audited repo, after `git fetch origin`:

```
python3 ~/.agents/skills/implement/codex-audit.py run
```

`codex-audit.py`'s docstring is the contract: its steps, its files and
what each exit means. This table is only what you do about each:

| Exit | What you do |
|---|---|
| 0 | Step 2. |
| 5 | Read the findings from the `.out` it names, then step 2. |
| 3 | Nothing. The week is recorded. |
| 6, or 0 or 5 with `left out:` lines | Report each left-out ticket to Chris: its skip was never audited, and it is left out again every week until its merge commit closes it in a form the range script reads. |
| 20 | Nothing this window. Tell Chris if the cap, not the kill switch, stopped it: the reserve did not hold. |
| 30 | Retry once later in the window; a second 30 goes to Chris. |
| 4 | Report it to Chris with its `.out`; never relaunch silently. |
| 2 | Fix the cause it names. When it says Codex already ran, do not relaunch: append that record's row by hand (`review_ledger.py append --type codex-audit --record <it>`) and go on to step 2. A missing mark line is written once with `codex-audit.py mark --sha <the newest merge already reviewed>`. |

## 2. Confirm

Each printed finding names the audited PRs whose merge touched its file.
For each finding, read the code at the range's newest merge and decide:

- **Confirmed**: the failure it describes happens, under the
  reachability bar of `SKILL.md` § Review. Find the PR that introduced
  it — the one printed, or `git log` on the lines when none was. A
  finding whose cause predates every audited PR is still confirmed; its
  ticket says so in place of an originating PR.
- **Disputed**: say why in one line. It goes in the trial row, not a
  ticket.

## 3. File

One ticket per confirmed finding, through `/file-ticket`, in the repo the
audit ran on. On top of what `file-ticket` requires, each one carries:

- the `ready-for-agent` label (and `bug` when it is one);
- a line `Found by the Codex audit of <YYYY-MM-DD> (range <range>).`;
- a line `Originating PR: #<pr> (ticket #<t>).`, or the sentence saying
  it predates the audited PRs.

## 4. Close out

One auto-ship commit on `main` of this skills repo, after every ticket is
filed:

1. Append the trial row to `docs/research/2026-09-14-codex-review-trial.md`:
   `audit <YYYY-MM-DD> (<repo>)` in the Ticket column, the audited PRs in the
   PR column, then the three counts — confirmed, also found by Claude (the
   PR's own round-1 review raised it, per its body's Decisions made), and
   disputed — and one line per confirmed finding with its filed ticket,
   then `not audited: ticket #<t>` for each left-out ticket.
2. Move the mark, run from the audited repo's checkout:
   `python3 ~/.agents/skills/implement/codex-audit.py mark --sha <newest merge>`,
   the sha the `next:` line names. It writes the trial doc in the
   skills checkout the script lives in.

The mark moves only here, so PRs from a run that stopped, or whose findings
were never filed, are audited again next week.

## Dry run

`--dry-run` (its docstring) spends no quota and posts nothing; copy the
real ledger in as `--ledger` to dry-run against real skips. While the kill
switch exists it stops at the gate like a real run.
