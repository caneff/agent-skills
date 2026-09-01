# Central coordinator agents: prior art

Research for [#487](https://github.com/caneff/agent-skills/issues/487) — the prior-art half.
The harness fact about subagent working directories is settled separately; this
document is about **what people have actually done with one agent fronting many
repositories or many workers, and what broke**.

Sources are labelled by kind:

- **[official]** — vendor documentation or the vendor's own engineering write-up.
- **[first-hand]** — a practitioner reporting their own lived experience, or a
  bug report filed by the person who hit it.
- **[secondary]** — commentary about someone else's system. Used only where no
  primary source exists, and flagged as such.

Researched 2026-09-01.

---

## Shape 1 — one long-running lead that spawns subagents (in-process)

**Who does this:** Anthropic's own Research product, and the standard Claude Code
`Agent`-tool pattern.

Anthropic's Research feature is an orchestrator-worker system: "a lead agent
[that] coordinates the process while delegating to specialized subagents that
operate in parallel", spinning up 3-5 subagents per query and synthesising their
findings
([official](https://www.anthropic.com/engineering/multi-agent-research-system)).
They report a 90.2% improvement over a single agent on their internal
research eval — but that is a *research* benchmark, not a coding one, and they
say so explicitly (see failure F8 below).

Claude Code's subagents are the same shape at a smaller scale: each subagent gets
its own context window, and its final report returns to the lead as an `Agent`
tool result
([official](https://code.claude.com/docs/en/sub-agents)).

**What Anthropic reports broke** (all
[official](https://www.anthropic.com/engineering/multi-agent-research-system)):

- Early lead agents were "spawning 50 subagents for simple queries".
- Subagents "duplicate work, leave gaps, or fail to find necessary information";
  in one case they "performed the exact same searches as other agents".
- "Synchronous execution creates bottlenecks" — the lead could not steer
  subagents while they ran.
- "Minor changes cascade into large behavioral changes"; "one step failing can
  cause agents to explore entirely different trajectories."
- Agents "scouring the web endlessly for nonexistent sources" — poor effort
  calibration.

**The counter-position, from a company that ships a coding agent.** Cognition's
"Don't Build Multi-Agents" is the strongest primary argument against this shape
for *coding*
([official / first-hand](https://cognition.com/blog/dont-build-multi-agents)).
Their two principles: "Share context, and share full agent traces, not just
individual messages", and "Actions carry implicit decisions, and conflicting
decisions carry bad results." Their worked example: asked to build Flappy Bird,
one subagent produces a Super Mario-style background and another a bird that does
not match it, because "Subagent 1 and subagent 2 cannot see what the other was
doing and so their work ends up being inconsistent with each other." They judge
that "agents today are not quite able to engage in this style of long-context
proactive discourse", and recommend a **single-threaded linear agent** where "the
context is continuous", with an LLM-based compression step for long tasks.

Cognition's position has since softened rather than reversed: the current
formulation is that multi-agent works "when writes stay single-threaded and the
additional agents contribute intelligence rather than actions"
([secondary](https://jxnl.co/writing/2025/09/11/why-cognition-does-not-use-multi-agent-systems/)
summarising Cognition; the sharpened wording is not on the original post, so
treat the softening as second-hand).

**Anthropic's own guidance agrees more than it disagrees.** Their "when to use
multi-agent systems" post says to start with single agents, that multi-agent
"typically use 3-10x more tokens than single-agent approaches for equivalent
tasks", that in one studied failure subagents "spent more tokens on coordination
than on executing", and warns of teams that "invest months building elaborate
multi-agent architectures only to discover that improved prompting on a single
agent achieved equivalent results"
([official](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)).
Critically for a per-repo split: decomposition by **problem type** (planning,
implementation, testing, review) "consistently fails"; work should be split along
**context boundaries** instead. A per-repository split *is* a context boundary,
which is the one thing this document found in the coordinator model's favour.

---

## Shape 2 — a lead session coordinating separate Claude Code sessions (agent teams)

Claude Code ships this: one session is the team lead, teammates are independent
Claude Code instances with their own context windows, coordinating through a
shared task list and a mailbox
([official](https://code.claude.com/docs/en/agent-teams)). It is **experimental
and disabled by default** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`).

The documented **Limitations** section is itself a first-party failure-mode list:

- **No session resumption with in-process teammates.** `/resume` and `/rewind`
  do not restore them, and "the lead may attempt to message teammates that no
  longer exist."
- **Task status can lag.** "Teammates sometimes fail to mark tasks as completed,
  which blocks dependent tasks."
- **The lead stops early.** "The lead can stop early too, deciding the team is
  finished before all tasks are actually complete."
- **The lead starts doing the work itself** instead of waiting for teammates —
  documented under best practices with a prompt to correct it.
- **Agents stopping early**: "Teammates may stop after encountering errors
  instead of recovering."
- **No nested teams**, **one team per session**, **lead is fixed** for the
  session's lifetime.
- **Permission prompts all bubble to the lead**, which the docs call out as
  friction.
- Before v2.1.207, a single malformed mailbox entry "caused a repeated error
  every second and blocked delivery for that mailbox until you deleted the file
  manually."

Docs guidance on size: start with 3-5 teammates; "beyond a certain point,
additional teammates don't speed up work proportionally"; and — directly relevant
here — "For sequential tasks, same-file edits, or work with many dependencies, a
single session or subagents are more effective."

**Cross-repo:** the agent-teams page says nothing about teammates running in
other repositories. Teammates load "the same project context as a regular
session: CLAUDE.md, MCP servers, and skills" — i.e. the lead's project. Checked
the whole page; **no cross-repository placement is documented**.

---

## Shape 3 — a coordinator that messages independent per-repo sessions

Claude Code's cross-session messaging is the documented shape for "a coordinator
that hands off to separate per-repo sessions by message"
([official](https://code.claude.com/docs/en/cross-session-messaging)). Sessions
are started and steered by you, run wherever you started them (so genuinely one
per repo), and Claude discovers them with `ListAgents` and messages them by name
with `SendMessage`. It works on Linux including WSL 2 (v2.1.224+).

This is the only shape found that is documented to span repositories without
qualification: `/list-agents` shows each local session's working directory
precisely so you can tell same-named sessions in different directories apart.

**Documented failure modes** (all
[official](https://code.claude.com/docs/en/cross-session-messaging)):

- **Messages can be held or refused, not just delivered.** With no explicit
  `crossSessionInbound` setting, the default is decided by the two sessions'
  permission modes: a receiving session that *bypasses* permission prompts
  **holds every message for your approval**, and a held dialog left unanswered
  past `dialogExpiry` (5 minutes by default) is **dropped**. A coordinator
  driving `--dangerously-skip-permissions` workers hits this by default.
- **Bursts are refused at the sender**; the receiver rate-limits per sender,
  drops identical repeats, and queues at most 50 messages. Before v2.1.236 those
  sends were reported as *sent* while the receiver dropped them.
- **Plain text only** — no structured protocol messages between independent
  sessions, and never the sender's history or files.
- **Idle notification is one-shot and expires after 12 hours**; a subagent or
  teammate cannot subscribe at all.
- **A container or WSL boundary blocks discovery entirely** — sessions register
  in files under the home directory, so a WSL 2 session and a native Windows
  session on the same machine cannot reach each other.
- A message from another session **cannot approve anything**, cannot change
  config, and any `/command` in it arrives as inert text.

**Agent view** is the matching surface: `claude agents` shows every background
session **across all projects** by default, `@<repo>` in the dispatch prompt
targets a specific directory, `--cwd` scopes the view, and each session reads
settings from its own directory
([official](https://code.claude.com/docs/en/agent-view)). Documented limits: you
cannot filter the dispatch input by project directory, and `/resume` inside a
scoped view only works for the repository you opened it from.

---

## Shape 4 — hand-rolled coordinators (tmux, file-based state)

`primeline-ai/claude-tmux-orchestration` is a first-hand build of exactly the
"orchestrator window + worker Claude Code sessions" model, with file-based state
in an `_orchestrator/` directory
([first-hand](https://github.com/primeline-ai/claude-tmux-orchestration)).

What the machinery exists to compensate for is the finding:

- A **bash heartbeat loop polling every 30-300 seconds** exists because Claude
  Code cannot self-coordinate without external polling — a worker "cannot check
  peer worker status or signal readiness on its own". Idle is detected by
  scraping terminal output with ANSI stripping.
- A **`.ready` file handshake** exists to prevent prompt collisions; multiline
  prompts need `load-buffer`/`paste-buffer` to dodge `send-keys` races.
- A **rate-limit watchdog** detects `429`/`overloaded` and backs off 65 seconds.
- Workers run with `--dangerously-skip-permissions`; the README says "Do not run
  this on production systems or with access to sensitive credentials."
- **Workers are single-repo**: "Workers run in your project directory only
  (scoped via `cd $PROJECT_ROOT`)." Even the hand-rolled coordinator did not
  place workers across repositories.
- The author's own retraction, July 2026: the original pitch is "no longer true"
  now that subagents have `maxTurns`, hooks, MCP servers and isolated contexts —
  "Try subagents first." Scaling advice: "Start with 2 and measure your own
  overhead."

The lasting lesson from this shape: **a coordinator that only receives push
notifications loses workers.** Every hand-rolled system in this class grows a
poller and a state file.

---

## Shape 5 — framework supervisor patterns (LangGraph and similar)

The published supervisor pattern is the same architecture outside Claude Code.
I could not reach a first-party LangGraph write-up of production failures; what
follows is from practitioner write-ups
([secondary/first-hand mixed](https://focused.io/lab/multi-agent-orchestration-in-langgraph-supervisor-vs-swarm-tradeoffs-and-architecture),
[secondary](https://www.buildmvpfast.com/blog/langgraph-supervisor-deep-agents-multi-agent-patterns-2026)):

- The supervisor is "a single point of failure and a latency/token bottleneck.
  Every decision awaits its reasoning."
- **Misrouting poisons everything downstream**, and an "infinite delegation loop"
  occurs when the supervisor keeps re-routing to the same worker because the
  worker's output never satisfies the completion condition.
- An LLM supervisor adds a model call to every request purely for routing, and
  its prompt "needs almost as much tuning as the specialist prompts."

Treat these as directionally corroborating Anthropic and Cognition rather than as
independent evidence — I did not find a named production post-mortem behind them.

---

## Failure modes, with how well each is evidenced

The issue named six suspected failure modes. Verdict on each:

| # | Failure mode | Verdict | Strength |
|---|---|---|---|
| F1 | Coordinator context exhaustion over a long session | **Confirmed, but indirect** | Medium-strong |
| F2 | Coordinator loses track of delegated work | **Confirmed** | Strong |
| F3 | Worker reports never arriving back | **Confirmed, first-hand bug reports** | Strong |
| F4 | Repos drifting out of sync | **Confirmed for multi-repo agents generally** | Medium |
| F5 | Coordinator becomes the bottleneck | **Confirmed** | Strong |
| F6 | Cost | **Confirmed with vendor numbers** | Strong |
| F7 | Conflicting decisions between workers who cannot see each other | **Confirmed** | Strong |
| F8 | Multi-agent is a worse fit for coding than for research | **Confirmed by the vendor** | Strong |

### F1 — coordinator context exhaustion

No source I found reports "my coordinator ran out of context after N days" with
numbers. What is documented:

- Anthropic: "If the context window exceeds 200,000 tokens it will be truncated"
  ([official](https://www.anthropic.com/engineering/multi-agent-research-system)).
- Claude Code's own costs page has a section titled **"Why usage climbs in a long
  session"**: the full conversation is sent with every request; cache misses
  after an idle break reprocess the whole context; **cross-session messages
  themselves start a new turn that sends the full context each time**; and
  `/compact` "is itself a large request"
  ([official](https://code.claude.com/docs/en/costs)). A coordinator's job is
  precisely to sit idle and absorb inbound messages, which is the pattern this
  section flags as expensive.
- Practitioner framing: "context rot… tokens earlier in the context window lose
  influence as more tokens are added", producing implementation drift where
  "final code barely resembles the original design"
  ([first-hand, but the token figures in that post are the author's illustrative
  estimates, not
  measurements](https://responseawareness.substack.com/p/claude-code-subagents-the-orchestrators)).

So: the mechanism is documented by the vendor, the lived report is qualitative.
**I could not find a quantified account of a coordinator dying of context over a
multi-day burndown.**

### F2 — coordinator loses track of delegated work

Strongest evidence is first-party and blunt: agent-team teammates "sometimes fail
to mark tasks as completed, which blocks dependent tasks", and "the lead can stop
early too, deciding the team is finished before all tasks are actually complete"
([official](https://code.claude.com/docs/en/agent-teams)). The lead also drifts
into doing the work itself instead of waiting. Addy Osmani's survey of the
pattern names the same thing: "the orchestrator itself is an agent, and the thing
meant to keep everyone on track drifts too"
([first-hand/secondary blend](https://addyosmani.com/blog/code-agent-orchestra/)).
The tmux orchestrator's 30-second heartbeat is the engineering response to it.

### F3 — worker reports never arriving back

This one is confirmed by bug reports read first-hand in the tracker:

- [anthropics/claude-code#54323](https://github.com/anthropics/claude-code/issues/54323)
  (**closed**): "Claude Code 2.1.56 consistently fails to return responses from
  subagent tasks… Tasks complete successfully but output is silently dropped,
  showing only 'Claude Code finished without returning a reply.'" Reported
  frequency: 100%.
- [anthropics/claude-code#56869](https://github.com/anthropics/claude-code/issues/56869)
  (**closed**): a subagent returning "Tool result missing due to internal error"
  gives the parent no error signal — "no timeout, no retry path, and no visible
  exception. From the user's side, it looks like Claude Code has hung."
- Also filed, not read in full:
  [#4371](https://github.com/anthropics/claude-code/issues/4371),
  [#43465](https://github.com/anthropics/claude-code/issues/43465) (subagent
  silently produces garbage instead of reporting extraction failure).

Both headline issues are closed, so these are historical regressions rather than
standing defects — but they are exactly the failure the coordinator model is most
exposed to, because a lost report is invisible to the lead.

The docs' own escape hatch confirms the shape: for background subagents,
"a background subagent's results reach Claude as a completion notification in a
later turn"
([official](https://code.claude.com/docs/en/sub-agents)) — a notification is a
push, and a push that is dropped is not retried.

### F4 — repos drifting out of sync

The best primary source is GitHub's own answer on the tracker. Asked how to use
background agents for changes spanning several repositories, a GitHub architect
answered that "background agents work best within a single repo context. For
multi-repo scenarios, breaking the work into repo-specific sub-tasks is currently
the most effective approach", noting **no supervisor agent capability exists to
coordinate work across repositories** and that changes cannot be tested in
isolation across service boundaries
([official answer on a first-hand
question](https://github.com/orgs/community/discussions/186469)). Their
recommended workaround is per-repo sub-issues assigned sequentially, plus a human
review loop to catch integration mismatches.

More generally: each agent has its own context window with no automatic
visibility into other agents' changes, so "Agent A's changes can invalidate Agent
B's assumptions without Agent B receiving any signal" — the standard multi-repo
account
([secondary, aggregated](https://bishoy.io/posts/ai-coding-assistants-multi-repo-solutions);
**note:** I fetched this piece expecting a practitioner post-mortem and it is
prescriptive, not retrospective — no case study, no numbers. Do not cite it as
experience).

### F5 — coordinator as bottleneck

Anthropic: "synchronous execution creates bottlenecks"; the lead waits on
subagents and cannot steer them mid-flight
([official](https://www.anthropic.com/engineering/multi-agent-research-system)).
Claude Code docs: "more teammates means more communication, task coordination,
and potential for conflicts", with diminishing returns
([official](https://code.claude.com/docs/en/agent-teams)). The supervisor
literature says the same in stronger terms — every decision waits on the
supervisor's reasoning. Addy Osmani's mitigation is to route around the lead
entirely: "Backend tells Frontend the API contract without the lead as
intermediary"
([first-hand/secondary](https://addyosmani.com/blog/code-agent-orchestra/)).

Osmani also names the constraint that matters most for a solo dev burning down
tickets: "The bottleneck is no longer generation. It's verification."

### F6 — cost

Vendor numbers, all official:

- Multi-agent systems use **~15x more tokens than chat**; agents alone ~4x
  ([Anthropic engineering](https://www.anthropic.com/engineering/multi-agent-research-system)).
- Multi-agent implementations "typically use **3-10x more tokens** than
  single-agent approaches for equivalent tasks"
  ([Anthropic](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)).
- Claude Code: "Agent teams use approximately **7x more tokens** than standard
  sessions when teammates run in plan mode"
  ([official](https://code.claude.com/docs/en/costs)).
- An in-process teammate's requests fall outside the main conversation's cache
  TTL bucket, so its cache holds for **five minutes** by default unless you set
  `subagentPromptCacheTtl` to `1h` — and 1-hour cache writes bill higher
  ([official](https://code.claude.com/docs/en/agent-teams)).

### F7 — conflicting decisions between workers

Cognition's core argument, above. Claude Code says it plainly too: "Two teammates
editing the same file leads to overwrites. Break the work so each teammate owns a
different set of files"
([official](https://code.claude.com/docs/en/agent-teams)). For 4-5 *separate*
repos this failure mode is largely designed away — different repos are different
files — except where the repos are coupled (shared skill, shared schema, one repo
consuming another's output).

### F8 — coding is the wrong domain for this

Anthropic, in the post that advertises their multi-agent system, disqualifies
coding from it: "Most coding tasks involve fewer truly parallelizable tasks than
research", and "LLM agents are not yet great at coordinating and delegating to
other agents in real time"
([official](https://www.anthropic.com/engineering/multi-agent-research-system)).
That is the vendor's own limit on their own headline result.

---

## The question actually asked: 4-5 repos, ready tickets, one at a time

**Honest answer: the reported experience does not favour a central coordinator
for this, and nobody has reported doing exactly this.**

Three reasons, in order of how well evidenced they are:

1. **The workload is sequential, and every source says sequential kills the
   case.** The ticket batch is burned down *one at a time*. Claude Code's own
   docs: "For sequential tasks, same-file edits, or work with many dependencies,
   a single session or subagents are more effective"
   ([official](https://code.claude.com/docs/en/agent-teams)). Anthropic's
   multi-agent guidance says the 90.2% result came from parallel breadth-first
   *research*, and that coding has "fewer truly parallelizable tasks"
   ([official](https://www.anthropic.com/engineering/multi-agent-research-system)).
   A coordinator that dispatches one worker and waits is paying the full
   coordination tax for none of the parallelism benefit — it is a single-threaded
   agent with an extra hop and an extra context window.

2. **The cross-repo placement the model needs is not documented anywhere, by
   anyone.** GitHub's architect: "no supervisor agent capability exists to
   coordinate work across repositories", multi-repo is "on the roadmap"
   ([official](https://github.com/orgs/community/discussions/186469)). Claude
   Code subagents start in "the main conversation's current working directory",
   and worktree isolation branches from the *parent repository's* default branch
   ([official](https://code.claude.com/docs/en/sub-agents)). Agent teams
   document no cross-repo placement. Even the hand-rolled tmux orchestrator
   scopes every worker to a single `$PROJECT_ROOT`
   ([first-hand](https://github.com/primeline-ai/claude-tmux-orchestration)).
   Four independent shapes, same answer.

3. **Where the coordinator has been tried, the machinery it grows is
   book-keeping, not intelligence** — heartbeats, ready-files, state JSON, idle
   polling. That is a scheduler. Sequential ticket burndown across 4-5 repos does
   not need an LLM to schedule it.

**What the sources *do* favour for this workload:** the "one view" requirement is
met without a coordinating LLM at all. `claude agents` shows every background
session across all projects by default, `@<repo>` dispatches into a named
repository, each session reads its own project's settings, and `Ctrl+S` groups
the list by directory
([official](https://code.claude.com/docs/en/agent-view)). Cross-session messaging
then covers the cases where one repo's session needs to tell another's what
landed
([official](https://code.claude.com/docs/en/cross-session-messaging)) — which is
precisely the "nearest workable version" the issue asked to record if placement
turned out to be impossible.

The one argument *for* the coordinator that survives: Anthropic says to split
work along **context boundaries**, not problem types
([official](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)),
and one-repo-per-worker is a clean context boundary. That makes a coordinator a
defensible shape for genuinely parallel cross-repo work. It does not make it the
right shape for a queue drained one ticket at a time.

---

## What is not documented, and what I checked

- **A quantified coordinator context-exhaustion account.** Searched for
  practitioner reports of long-running orchestrators losing the thread over
  days/weeks. Found the mechanism documented officially (Claude Code's "Why usage
  climbs in a long session") and qualitative "context rot" accounts, but **no
  numbers from a real multi-day coordinator run**.
- **Anyone running a coordinator over 4-5 separate repos with a ticket queue.**
  Checked Anthropic engineering, Claude Code docs (agent-teams, sub-agents,
  agent-view, cross-session-messaging, costs), the GitHub community tracker,
  Cognition, and practitioner write-ups. The closest is GitHub's discussion
  #186469, and the answer there is "don't — decompose per repo."
- **First-party LangGraph production failure data.** Only practitioner and
  content-marketing write-ups were reachable; treated as directional.
- **Whether the closed subagent-report bugs (#54323, #56869) recur.** Both are
  closed; I did not find an open successor, but I did not exhaustively sweep the
  tracker.
- **`levelup.gitconnected.com` "What 371 Git Worktrees Taught Me About
  Multi-Agent AI"** looked like the best first-hand numbers source in the search
  results; it returned HTTP 403 and I could not read it. Flagging it as an
  unexamined lead.

## Bottom line

The central coordinator is a real, shipped, documented shape — three times over
inside Claude Code alone (subagents, agent teams, cross-session messaging) — and
the vendor that built the most successful version of it says in the same
breath that coding is not the domain for it and that agents "are not yet great at
coordinating and delegating to other agents in real time"
([official](https://www.anthropic.com/engineering/multi-agent-research-system)).
The failure modes the issue guessed at are all real and mostly documented by the
vendors themselves; the best-evidenced ones are losing track of delegated work,
reports vanishing on the way back, and cost at 7-15x.

For 4-5 repos and a queue drained one ticket at a time, the prior art points at
**separate per-repo sessions with `claude agents` as the one view**, not at a
coordinating LLM. Nobody reports having made the coordinator version work for
this workload; several vendors report the pieces it would need not existing.
