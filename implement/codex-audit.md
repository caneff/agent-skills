# Weekly Codex audit

Once per Codex quota window, one Codex adversarial review covers every
merged PR that skipped its merge-gate pass for size or the reserve ceiling
(`SKILL.md` § The merge step 3). Confirmed findings become one
`ready-for-agent` ticket each. The controller running it owns every step
below; no worker is involved, and nothing is posted to the merged PRs.

Run it near the end of the window, by hand or when the weekly retro points
at it: the reserve above 70 % exists for this run, and it is spent only
when the window is about to reset. The reset time is the one the usage
gate prints.

## 1. Run

From the primary checkout of the audited repo, after `git fetch origin`:

```
python3 ~/.agents/skills/implement/codex-audit.py run
```

`codex-audit.py`'s docstring is the contract: the steps in order, the
files it writes under `~/.cache/agent-reviews/<repo>/`, and the exit
statuses. Each stop appends one `codex-audit` ledger row saying why, so a
week with no audit is never read as a week audited clean, and no stop moves
the audit mark. Read the exit before anything else:

| Exit | Meaning | What you do |
|---|---|---|
| 0 | Codex ran; findings, or `no material findings`, are printed | Step 2 |
| 3 | No PR skipped since the mark | Nothing. The week is recorded. |
| 20 | Capped or the kill switch | Nothing this window. Tell Chris if the cap, not the switch, stopped it: the reserve did not hold. |
| 30 | No usage reading | Retry once later in the window; a second 30 goes to Chris. |
| 4 | The Codex run exited non-zero | Its `.out` says why. Report to Chris; never relaunch silently. |
| 5 | Codex output the ledger cannot read as findings | Read the `.out` yourself, then step 2 with the findings you find in it. |
| 2 | A usage, git, `gh` or ledger error, or no mark line for this repo | Fix the cause it names. A missing mark line is written once with `codex-audit.py mark --sha <the newest merge already reviewed>`. |

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
   disputed — and one line per confirmed finding with its filed ticket.
2. Move the mark, run from the audited repo's checkout:
   `python3 ~/.agents/skills/implement/codex-audit.py mark --sha <newest merge>`,
   the sha exit 0's `next:` line names. It writes the trial doc in the
   skills checkout the script lives in.

The mark moves only here, so PRs from a run that stopped, or whose findings
were never filed, are audited again next week.

## Dry run

`run --dry-run --ledger <copy> --cache <dir>` takes every step but the
Codex launch, which writes `--simulate-out` (default no findings) and
exits `--simulate-status` (default 0). It spends no quota and posts
nothing. It needs both paths named so that it never appends to the real
ledger; copy the real one in to dry-run against real skips.
`codex_audit_test.py` walks every exit this way.
