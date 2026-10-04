# Ablations

One review component is switched off at a time (ADR 0005), and kept only if
the review ledger shows bugs escaping without it. Each ablation is a section
here whose heading ends in its state, `running` or `ended`. A worker reads the
heading to know whether the component runs; a controller appends to the log
when a burn closes and brings Chris the table when the third burn has.

## Codex pass — running

- **Off:** the Codex pass of the review wave, on every PR. The three review
  axes run as before.
- **Mechanism:** the kill-switch file `~/.config/agent-skills/codex-reviews-off`
  (#1354), read by `implement/codex-usage-gate.py`, which then exits 20 with
  `codex reviews off by Chris's ruling`. A worker appends its ledger skip row
  with `--skip-reason ablation` and names the printed line in the PR body.
  Removing the file ends the ablation.
- **Started:** 2026-10-04, by Chris's ruling (option a). It runs for three
  closed burns or drain runs.
- **Why this one:** on 2026-10-04 no PR ran the pass anyway. Of eight merged,
  six were under the size threshold and two hit the 70% reserve ceiling.
- **Measure:** `python3 ~/.agents/skills/docs/research/review_ledger.py
  escapes --repo-dir <checkout>`; the component is the Codex pass's
  `ablation` skip rows.
- **Decision rule:** keep the Codex pass if the table attributes any escape to
  it, and delete it from the wave otherwise. Read each listed escape first, as
  below. The controller brings Chris the table; Chris rules.

## Standards axis on small PRs — ended

- **Ended:** 2026-10-04 by Chris's ruling, "i dont want to test this one standards always on",
  before any burn closed with the table. The standards axis runs on every PR.

- **Off:** the standards axis of `/multi-axis-code-review` on a PR under the
  #1357 size threshold. The other two axes and Codex run as before. A PR at or
  above the threshold runs all of them.
- **Started:** with #1401's landing. It runs for three closed burns.
- **Measure:** `python3 ~/.agents/skills/docs/research/review_ledger.py
  escapes --repo-dir <checkout>`; the component is `standards:ablation` in its
  table. A skipped run is recorded in the ledger by `append --type standards
  --skip-reason ablation`, so the count has something to attribute to.
- **Decision rule:** after the third closed burn, keep the standards axis on
  small PRs if the table attributes any escape to `standards:ablation`, and
  delete its run from the small-PR path otherwise. The controller brings Chris
  the table and the rule's answer; Chris rules, and the heading becomes `ended`.
  Read each escape the table lists before answering: it is matched by a commit
  subject (a fix, a bug, a regression) and a `git blame` of the lines it
  changed, so a false match is possible and one is not a reason to keep.

### Log

One line per closed burn: date, run id, small PRs that skipped the axis,
escapes attributed so far.
- 2026-10-04, burn-trs-2026-10-04 (twitch-rules-scroller): 1 small PR skipped the axis (#608); 0 escapes attributed so far.
