---
name: audit-instructions
description: Audit instruction text against Anthropic's current published guidance and report what to delete. Slash-only.
disable-model-invocation: true
argument-hint: "[path ...]"
---

Audit instruction text — a `CLAUDE.md`, a skill's `SKILL.md`, a hook prompt, a system
prompt — against what Anthropic publishes **today**, and report what to cut.

Targets: the paths in `$ARGUMENTS`, else the `CLAUDE.md` chain in scope.

Read-only. Report the verdicts; the user applies them.

## 1. Fetch the receipts

Read every URL in `SOURCES.md`, plus the page for the exact model running this session.
Use what is published today, never what you remember — recalled guidance is not a receipt.

A fetch that fails is **NOT RUN**: report it and stop.

Done when every source is fetched or named NOT RUN.

## 2. One verdict per instruction

Go line by line. Every instruction gets one **verdict** — DELETE, KEEP, or REWRITE —
with the reason in plain English.

**No receipt, no delete.** A DELETE quotes the sentence from the fetched guidance that
justifies it. Cannot find one? The verdict is KEEP. Never invent a receipt.

Done when every instruction line in every target file carries a verdict.

## 3. Flags

Where to look. A flag points; the quoted guidance decides.

- **Verify-twice** — "always verify your work", "double-check before answering". The model
  already self-corrects. These make it do the work twice, and the user pays for both.
- **"Only flag the big issues"** — taken literally, so the user gets told less than they
  wanted. Rewrite as: report everything, I do the filtering.
- **"Don't overthink"** — rules against thinking make internal tags leak into the answer.
- **Role padding** — "you are an expert with 20 years of experience" was once good advice,
  now optional. Keep a role only where it genuinely changes the output.
- **Stale examples** — examples written for an old model teach old habits. One current
  example beats ten stale ones.

**Truth rules are protected.** "Only claim what you verified" is not a severity filter, it
stops made-up facts. Rules like that stay, whatever else goes.

Fetched guidance outranks any flag here. When it does, say so in the report.

## 4. What is missing

Current models often want steering older files lack — keep answers short, cap document
length, say how to update me while you work, hold the task scope, limit the helpers you
spawn. Treat these as candidates, not a checklist to fill.

Before surfacing any addition, classify it:

- **Repo-specific gap** — a fact about *this* repo, its code, or its workflow that the file
  omits. Worth adding. Give exact paste-ready wording.
- **Generic steering** — advice that fits any repo and belongs in the reader's global
  `CLAUDE.md`, persona, or harness config, not a repo file. Drop it, or name it once as
  "your global, not this repo file" — never emit it as a repo edit. On a lean chain the
  reader already sets these globally, so proposing them is bloat-by-addition.

Check each candidate against the fetched guidance and against what the target file (and its
`CLAUDE.md` chain in scope) already says — an existing line covering the ground means no gap.

Never emit steering pinned to one model page as a durable repo line: if the only receipt is a
model-version page, it is that model's advice, not a fact about the repo, and it rots on the
next model change.

On a lean, owner-written chain, the honest result here is often **0 additions**. Report zero
when zero is true; do not manufacture five.

## 5. Report

The default deliverable is a self-contained HTML report, styled with the
**visual-teach** design system. Follow `~/.agents/skills/all-audits/harness/HTML-REPORT.md`
for the asset delivery (copy the `vt-*` assets beside the report and link them
relatively), the scaffold, and the styling — this skill only differs in what the
report holds. Write to `<tmpdir>/audit-instructions-<timestamp>/report.html`, then
open it and hand off the path as the harness's asset-delivery section describes
— print only the honest count and the report's absolute path.

- **Header** — a one-line verdict, then a `vt-metabar` with the **honest count**:
  "307 lines in · 4 delete · 4 rewrite · 5 additions."
- **Verdict rows** — one per instruction, in a `vt-table`: my line | verdict | why |
  Anthropic's line. Color the verdict `vt-pill bad` for DELETE, `vt-pill warn` for
  REWRITE, `vt-pill good` for KEEP.
- **Missing** — a section giving the **exact paste-ready wording** for each repo-specific
  gap section 4 surfaced. Often there are none; say so plainly rather than padding to five.
- **NOT RUN** — a `vt-callout warn` naming everything you could not check. Never a
  clean bill you did not earn.

If most of the file should go, say so plainly in the verdict. The scaffolding the
user is proudest of is the likeliest casualty.
