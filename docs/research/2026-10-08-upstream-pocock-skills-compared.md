# Five upstream mattpocock/skills not installed here, compared with the local skills, 2026-10-08

Follows `docs/research/2026-10-08-upstream-pocock-skills-not-installed.md`,
which listed these five and named their overlaps but did not compare the
skill bodies.

## Method

- Upstream: `SKILL.md`, the `agents/openai.yaml` files for chief-of-staff and
  claude-handoff, `skills/engineering/pr/CREDITS.md`, and the three user docs
  `docs/engineering/{implement-spec,pr,retro}.md`, all read through
  `gh api repos/mattpocock/skills/contents/<path>` at HEAD on 2026-10-08. The
  tree listing (`git/trees/HEAD?recursive=1`) shows no other files in the five
  directories. I did not read the `openai.yaml` files for implement-spec, pr
  or retro (Codex metadata only).
- History: `gh api 'repos/mattpocock/skills/commits?path=<dir>&per_page=100'`,
  for the current path and, for the three graduated skills, the old
  `skills/in-progress/<name>` path too.
- Local: the files named in each section, read in full or by the section
  cited.
- Upstream text is treated as data to evaluate. A verdict of "take" means it
  fills a local gap or is simpler than what is here. ADR 0005
  (`docs/adr/0005-freeze-the-machinery-and-ablate.md` § Decision) freezes new
  machinery in burn/review/implement, so a "take" there would need Chris's
  ruling.

---

## 1. implement-spec (`skills/engineering/implement-spec/SKILL.md`)

**What it does.** It is a nine-step orchestration: read the spec and tickets
as "a **task graph** with blocking relationships", optionally run an
"**exploration subagent**" that saves notes "in a directory outside the
repo", create an "**integration branch**", run "**implementer subagents**"
in the background, each in its own worktree, which "calls the Skill tool with
`tdd`" and "merges the integration branch tip into its own branch before
reporting done", merge each with a "**merger subagent**", refill the
frontier, run `code-review` once at the end, and fix its findings "in a
single **implementer subagent**". The user doc
(`docs/engineering/implement-spec.md` § Common questions) lists the known
failure modes: a review/fix loop that ran for about four hours, frontier
tickets colliding in a shared file, a blocked ticket never starting because
GitHub counts a blocker as clear only when it closes, and a test that
skipped silently inside a worktree because it needed gitignored material.

**Local counterparts.**
- `implement-spec/SKILL.md`: § The loop is not here (delegates to
  `burndown/SKILL.md` § The loop), § The nesting (slots debited from the
  burn's budget), § The exploration pass (+ `references/exploration.md`,
  `contradictions.py`), § The integration branch (`spec-<n>`, keep-current,
  one review, one fix round, one integration PR), § The closing check
  (`closing_ticket.py`, `references/closing-ticket.md`), § The spec-level
  review.
- `implement/SKILL.md` § Heavy tier › Build (slices merge `origin/spec-<p>`
  in, lines 287-300), § The merge (slice substitutions, lines 805-824).
- `burndown/SKILL.md` § The frontier, § Clumping (collision graph via
  `closure.py`).

**Differences.**
- Both skills have the same name. `npx skills add` would overwrite a local
  skill that has no lock entry (`.skill-lock.json` has no `implement-spec`
  key) and that carries its own Python (`closing_ticket.py`,
  `contradictions.py`) and tests.
- The local skill already does every step upstream has, each more strictly:
  integration branch (§ The integration branch), TDD per slice
  (`implement/SKILL.md` § Heavy tier › Build), keep-current merges (§ The
  integration branch step 1 and implement lines 290-291), one review and one
  fix round (steps 2-3).
- Upstream's documented failure modes are already handled here:
  - "Review/fix loop ran for hours": local caps it at "One review" and "One
    fix round", and ADR 0006 is the record.
  - "Two implementers collided on the same file": `burndown/SKILL.md`
    § Clumping and `burndown/references/loop.md` (a shared directory holds
    too, #1342).
  - "Blocked tickets never start": `burndown/SKILL.md` § The frontier, and
    commit `9b507712`, "a slice landed on spec-<p> no longer blocks the
    slices after it (#1469)".
- Upstream's exploration subagent writes notes that later subagents read.
  The local exploration pass checks decisions against the code and routes
  any contradiction to Chris (`references/exploration.md` § The three
  verdicts). The two passes do different jobs. The local one is the
  stricter of the two.
- One upstream point is only partly covered here: "A worktree holds only
  what git tracks. Tests that read gitignored fixtures, local databases, or
  credentials can silently skip there" (`docs/engineering/implement-spec.md`).
  The local text says this only for the mutation worktree
  (`implement/SKILL.md` § Heavy tier › Build, lines 246-248, #1219), not for
  the worker's own workspace. `rg -i 'gitignored|untracked'` over implement,
  implement-spec and burndown found nothing else. It is defect class 1 in
  `AGENTS.md` § Recurring defect classes, "Could this success have been
  produced by the thing not running at all?"

**Verdict: skip.** Upstream is a simpler subset of what the local skill
already does, its name collides, and its documented pitfalls are fixed here.
The one partial gap, a silent skip in the worker's workspace, is a
friction-log line if it ever happens (`burndown/SKILL.md` § The friction
log). It should not get new prose while ADR 0005 holds.

**Stability.** 3 commits at `skills/engineering/implement-spec`, all on
2026-09-24 (graduated, then two wording fixes `a31f3f68` and `c612defa`),
plus 4 at `skills/in-progress/implement-spec` from 2026-08-21 to 2026-09-24.
The skill is young but settled. Its last substantive change (`153fc1b9`,
2026-09-24) added the integration branch and TDD implementers.

---

## 2. pr (`skills/engineering/pr/SKILL.md`)

**What it does.** It is a PR-body template with three sections. **Summary**
is "the smallest view that makes the key point clear": pseudocode, a call
tree, a component tree, a file tree, Mermaid, or a shaped diff. That menu is
copied from Dex Horthy's `show-me` (`skills/engineering/pr/CREDITS.md`).
**Evidence** is a before and after ("Screenshots are S-tier",
"Execution-based evidence is A-tier ... Show the exact test that now fails
and passes"). **Merge Danger** names "**Door:** <one-way or two-way>" and
"**Blast Radius:**". It is model-invoked ("Use when writing a PR body."). The
doc calls the door call "the leading idea" and says to "be most suspicious
when it says 'two-way, small blast radius'" (`docs/engineering/pr.md` § The
template, § Common questions).

**Local counterpart.** `implement/SKILL.md` § The PR (lines 659-792). The
body has "these sections and nothing else": **Closes #<n>** (bare lines),
**What changed** (three lines), **Tests run** (command and result line),
**Decisions made** (every finding with its disposition, keyed by
`S1`/`P2`/`C3` ids), and **Last reviewed sha**. The "PR up" report adds
Mutation check, Parallel jobs and Cleanup blockers. § Before the PR step 6
checks `closingIssuesReferences`.

**Differences.**
- The audiences differ. The local body is read by a controller agent and by
  `fix-check.sh` / `merge-cleanup` (dispositions, closing refs). Chris's own
  repos "land unreviewed" (`~/.claude/CLAUDE.md` § Hard rules). Upstream's
  body is written for a human reviewer to scan.
- Upstream's "nothing else" rule conflicts with local § The PR's "these
  sections and nothing else". Installing `pr` would put two templates for
  the same document in front of the agent, the failure upstream's own doc
  describes (`docs/engineering/pr.md` § "My repo already has a PR
  template").
- Upstream's **Merge Danger** door call has no local equivalent in the PR
  body (`rg -i 'one-way|two-way|blast radius' implement burndown` found
  none). Locally, irreversibility is decided earlier and elsewhere:
  `~/.claude/CLAUDE.md` "STOP and ask before anything you cannot undo", and
  `burndown/SKILL.md` § What the controller says to Chris ("a decision that
  is contested or cannot be undone").
- Upstream's **Evidence** before/after is stronger than local **Tests run**:
  "'Tests are green' on its own is a claim, not a before and after"
  (`docs/engineering/pr.md`). Locally, before/after evidence is required
  only for a test or a gate (the **Mutation check** line in the PR-up
  report).

**Verdict: skip.** One idea could be taken later, with care: a one-line
**Door** (one-way / two-way) in `implement/SKILL.md` § The PR's section
list. It would only pay off on someone else's repo (`implement/SKILL.md`
§ Someone else's repo) or a `ready-for-human` PR, where a human actually
reads the body. Adding a section to the implement machinery is frozen by
ADR 0005, so this needs Chris's ruling. I would not offer it unprompted.
Installing the whole skill would fight the local template.

**Stability.** 2 commits at `skills/engineering/pr` (graduated `a7d038f6`,
CONTEXT.md→GLOSSARY.md rename `e484a809`, both 2026-09-24), plus 9 at
`skills/in-progress/pr` from 2026-09-17 to 2026-09-24, among them "Removed
HTML artifact section" and "Modified the PR body template to make it easier
to scan". The template is a week old and changed often before it graduated.

---

## 3. retro (`skills/engineering/retro/SKILL.md`)

**What it does.** You run it on one coding session, by default the current
one. It loads `writing-for-agents`, reads the session's primary sources, and
proposes environment fixes in seven categories: Navigation, Automated
checks, Coding standards, Global AGENTS.md, Tool economy, No-ops,
Information access. It presents them "in order of severity" and only
proposes. Its main points:
- "a check that already exists but sits unwired or silently broken is the
  finding, not a reinvention";
- "A repo with no **guardrail** ... is itself a finding";
- a **mechanical** violation "gets a deterministic check, full stop ...
  Default to building the check over writing the rule";
- standards belong to the reviewer because the implementer "has the most
  **context pressure**" (§ Reference › Implementation vs Review).

**Local counterparts.**
- The weekly retro, `/home/caneff/src/second-brain-v2/.claude/scripts/retro.py`
  (module docstring, `build_prompt`, `chris_messages`). The Sunday digest
  service runs it headless over 7 days of transcripts from all projects. It
  auto-lands RULE lines into `Memory/RULES.md` / `SOUL.md` and proposes
  retirements, SKILL candidates and FIXes.
- `.claude/skills/digest/SKILL.md` routes those proposals to issues on
  Chris's confirm.
- `Memory/RULES.md` line 1 (the retro inbox: a rule only after two
  occurrences, ruled 2026-10-04, ADR 0005 / #1401).
- `burndown/SKILL.md` § The friction log ("The weekly retro reads the log").

**Differences.**
- Most of upstream's categories are already in the local prompt.
  `build_prompt`'s item 3 (FIX) says "Sweep these five in particular":
  navigation, missing automated check, tool economy, information access,
  and a steering file grown too long. Item 1 (RULE) already routes a
  reviewer-only rule "as a FIX naming the repo's own standards file" and
  proposes retiring "no-ops". Upstream's reviewer-vs-implementer split and
  its no-op category are both covered.
- Scope and input differ. Upstream reads one session's full record,
  including tool calls. The local retro reads only "the turns Chris actually
  typed" (`chris_messages`: interactive `cli` entrypoint, non-meta,
  plain-string user content; tool results are dropped). So a session that
  burned twenty tool calls finding a file shows up locally only if Chris
  complained about it. That is a real blind spot for the navigation and
  tool-economy sweeps the prompt asks for. It is also deliberate:
  `chris_messages`' docstring says feeding more than Chris's turns caused
  false positives (#81).
- Not in the local prompt:
  - (a) An existing check that is unwired or silently broken is the
    finding.
  - (b) A repo with no guardrail is a finding.
  - (c) A mechanical violation gets a deterministic check rather than
    prose.

  `build_prompt` asks for "a mistake a lint, type check, or test would have
  caught (missing automated check)". It does not say to look for a check
  that already exists, and it does not ask the model to classify a
  violation as mechanical or judgement.
- Gap found while comparing, not in upstream: ADR 0005 § Decision says
  controller friction goes to `docs/agents/friction-log.md`, "read at
  retro", and `burndown/SKILL.md` § The friction log says "The weekly retro
  reads the log". `rg -n -uu 'friction-log|friction_log'` over
  `/home/caneff/src/second-brain-v2` (excluding `Digests/` and `.git/`)
  found no match. `retro.py` gets its input from `scan_transcripts` and
  `chris_messages` alone, so nothing feeds the log (22 lines today) to the
  retro. This is defect class 2 in `AGENTS.md` § Recurring defect classes:
  a stated rule with no mechanism behind it. I did not check whether a
  person reads the log by hand at retro time.
- Upstream has a gap of its own: it "does not audit the lint rules, hooks,
  or CI jobs it proposed last month" (`docs/engineering/retro.md`). The
  local retro has the rejected-items ledger (`Digests/rejected.json`) and
  rule retirement, which upstream lacks.

**Verdict: take specific ideas, not the skill.**
- Take (a) and (c) into `retro.py` `build_prompt`, item 3 (FIX):
  - "when an automated check would have caught it, first look for an
    existing one that is unwired or broken; that is the finding";
  - "a mechanical violation gets a deterministic check, not a standards
    line".

  (b) is better asked per repo in a hand-run session than in a weekly
  transcript distill, so I would leave it out. This is the vault repo, so
  ADR 0005's freeze on burn/review/implement does not apply, but the change
  is code (`retro.py` is executed), so it goes in the code lane.
- Skip installing `/retro` as a per-session skill. It would be a second
  retro loop, and the local rule is one retro with a two-occurrence bar
  (`Memory/RULES.md` line 1). Note, though, that the installed `ask-matt`
  tells users to "Run `/retro`" twice (`ask-matt/SKILL.md` lines 30 and 42)
  and that command does not exist here. That is a dangling pointer, to be
  fixed by removing those lines or by installing retro.
- Raise the friction-log gap above with Chris as a doc-vs-code
  contradiction. It is his to rule on: either the retro reads the log, or
  ADR 0005 and burndown § The friction log stop saying it does.

**Stability.** 1 commit at `skills/engineering/retro` (`a7d038f6`,
2026-09-24, graduated), plus 5 at `skills/in-progress/retro` from 2026-08-24
to 2026-09-24. The last substantive one is `0243b6ec` (2026-09-15), "push
mechanical coding-standards findings toward deterministic checks", which is
idea (c) above.

---

## 4. chief-of-staff (`skills/in-progress/chief-of-staff/SKILL.md`)

**What it does.** One long session pursues a goal as "the Directly
Responsible Individual". It thinks on two tracks, "Tactical: how do I
complete the immediate task?" and "Strategic: how do I modify the
environment to improve the outcomes of the _next_ task?". It suggests
recurring schedules, does "All work ... in subagents. Protect your context
window.", uses background agents, and talks to subagents through "**context
pointers**". Under § Strategic View: "As part of any and all work, FIRST
consider how the environment ... might be improved", build a "**pit of
success**" (constrained APIs, lint rules, CODING_STANDARDS.md), and follow a
"no workarounds" rule. It ends: "Be relentless in improving the environment.
Use every user message as an excuse to search for these improvements."

**Local counterparts.**
- `burndown/SKILL.md`: § The loop (controller dispatching workers, slots,
  refill), § What the controller says to Chris, § The friction log,
  § Parking and escalation.
- `implement-spec/SKILL.md` § The nesting (a controller of its own slices).
- `~/.claude/CLAUDE.md` § Work ("Never spin while a subagent or job is
  out") and § Hard rules ("A denied step is reported verbatim and stops;
  never reach it another way", which is the local "no workarounds").

**Differences.**
- Upstream drives a session toward a goal. Local burndown drains a queue.
  Locally, a goal goes through `/grill-me` → `/to-spec` → `/to-tickets`
  first (`~/.claude/CLAUDE.md` § Work), and `wayfinder` covers work bigger
  than one session.
- Upstream's strategic track ("FIRST consider how the environment might be
  improved", "Use every user message as an excuse") is the loop ADR 0005
  stopped. ADR 0005 § Context says 77% of 301 tickets in two weeks targeted
  the tooling, "Each friction point became a prevention ticket and each
  ticket more machinery". Its § Decision sends friction to one log, and a
  ticket comes only on the second occurrence (`burndown/SKILL.md` § The
  friction log).
- Background subagents, context pointers and "protect your context" are
  already local practice. See `burndown/SKILL.md` § The loop and
  `implement/SKILL.md` § The brief, where tickets are rendered by pointer.
- Upstream has nothing on budget, parking, merge ownership or reporting.
  Those are local hard rules.

**Verdict: skip.** Its main idea, improving the environment relentlessly on
every message, is what ADR 0005 was written to stop. Everything else in it
already exists here in a stricter form.

**Stability.** 5 commits, all between 2026-10-05 and 2026-10-06
(`e47c149e` "Added experimental chief-of-staff skill" through `6fd94792`
"Updates"). It sits in `in-progress/`, and two of its commit messages are
"More playing around" and "Updates". It is unstable.

---

## 5. claude-handoff (`skills/in-progress/claude-handoff/SKILL.md`)

**What it does.** It writes a handoff summary to the OS temp directory,
then launches a background agent seeded with it: `claude --bg --name
"<descriptive name>" -- "$(cat <summary file>)"`. The skill says "Passing
the file keeps the shell from running backticks or expanding `$` in the
summary". It requires `--name`, a "suggested skills" section, pointers
rather than duplication, and redaction. An argument tailors the summary.

**Local counterpart.** `handoff/SKILL.md`, installed from upstream
`skills/productivity/handoff/SKILL.md` per `.skill-lock.json` and last
merged 2026-10-06 (`ec6d50bd`). Its shared rules are Standalone, Suggested
skills, Redact secrets and focus. It always writes `/tmp/handoff-<slug>.md`
and has four modes. § File mode is the default: `/clear` then `/pickup`.
§ Agent mode hands Chris `! claude --bg --name "<descriptive name>" "Read
the handoff at /tmp/handoff-<slug>.md and continue the work."` § Sub mode
and § Side mode use the Agent tool.

**Differences.**
- Local § Agent mode does what claude-handoff does, with two differences.
  The local seed prompt is one fixed line pointing at the file, so the
  summary never passes through the shell and the backtick/`$` problem
  upstream fixed on 2026-10-06 (`07b7105a`, `4ec00d96`) cannot happen. And
  local hands Chris a `!` line to run instead of launching the agent itself.
- Upstream's prompt is the whole summary. Locally the agent reads the file,
  so the summary lives in one place, which local § Then, depending on mode
  calls "the summary lives in one place".
- Upstream writes to "the temporary directory of the user's OS". Local
  hard-codes `/tmp`, which is correct on this WSL shell (`~/.claude/CLAUDE.md`:
  "WSL is the shell only").

**Verdict: skip.** The local `handoff` already does this in its § Agent
mode, more safely. It has nothing new to take.

**Stability.** 10 commits between 2026-07-02 (`f8d12710` "Add
claude-handoff skill (in-progress)") and 2026-10-06. The last two, on
2026-10-06, fixed shell interpolation. It has been in `in-progress/` for
three months.

---

## Summary

| Skill | Verdict | One-line reason |
|---|---|---|
| implement-spec | skip | The local skill of the same name already does everything upstream does, more strictly, and fixes every pitfall upstream documents. Installing it would overwrite a hand-written skill that has its own code. |
| pr | skip (one idea needs Chris's ruling) | Its template conflicts with `implement/SKILL.md` § The PR, which machines read. The **Door** (one-way/two-way) line could help only on PRs a human reviews, and adding it is frozen by ADR 0005. |
| retro | take specific ideas | Add "an existing check that is unwired or broken is the finding" and "a mechanical violation gets a deterministic check" to `retro.py` `build_prompt` item 3. Do not install `/retro`. Separately: the weekly retro does not read the friction log, though ADR 0005 and burndown say it does, and `ask-matt` points at a `/retro` that is not installed. |
| chief-of-staff | skip | Its core instruction, to improve the environment on every message, is the ticket-inflation loop ADR 0005 froze. It is 2 days old and in-progress. |
| claude-handoff | skip | Local `handoff` § Agent mode already covers it, and its fixed seed line avoids the shell-interpolation bug upstream fixed on 2026-10-06. |
