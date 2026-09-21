# Jev — what it is, and whether it's useful to Chris

## What it is

Jev is the first "System One Model" from TypeSafe AI, a stealth-mode lab
founded by Diogo Almeida (ex-OpenAI, worked on the RLHF methods behind
ChatGPT), released into early access on 2026-09-15. It is not a chat LLM: it
takes unstructured state (text or JSON) plus a set of typed questions, and
returns typed answers — a label (`Choice`), a yes/no probability (`Noul`), or
an ordered score (`Score`) — with calibrated confidence, computed in parallel
in one pass rather than token-by-token. It cannot generate prose and, per
TypeSafe, cannot produce a malformed output (schema match is guaranteed by
construction, not by parsing a string).

- Access: early access / waitlist, API key from `console.typesafe.ai`.
- Pricing (per TypeSafe's own numbers): input $0.042/MTok, output free
  ("too cheap to meter" — no output tokens are generated).
- Speed: 70–500ms per call, claimed 40–200x faster than comparable LLMs on
  System One–shaped tasks.
- License/maturity: the model itself is a closed, hosted API in early
  access (\<1 week old as of this writing) — no self-hosting, no open
  weights. It is genuinely new and unproven at scale; TypeSafe's own
  post is the only public evidence of quality, alongside one third-party
  writeup (LangChain's blog, below) that repeats TypeSafe's numbers rather
  than independently verifying them.

Community tooling built on top in the same week (all early, low-adoption):
`jev-cli`, `jev-agent-tool` (both thin Python/CLI clients), `jev-harness`
(test-failure triage / "doom loop" guard for coding agents), `jev-use`
(TS/JS library), `jev-browser-pilot` (decision layer for browser automation),
and — most relevant to Chris — **jev-code** by François Chastel, an MCP
server + Agent Skill that wires Jev into Claude Code, Codex, Pi, and
OpenCode specifically. jev-code is MIT-licensed, 1 GitHub star, first commit
2026-09-19 (i.e., two days old, effectively unadopted).

## What it actually does (jev-code, since that's Chris's stack)

Exposes five tools (MCP for Claude Code/Codex, native extension for Pi,
custom tool for OpenCode, or a bare CLI):

| Tool | Use | Returns |
|---|---|---|
| `jev_classify` | label many items from a fixed class set | label, full probability distribution, margin, `decision: auto\|review` |
| `jev_check` | one yes/no question about one piece of evidence | probability, `verdict: yes\|no\|uncertain` |
| `jev_score` | many items on one ordered scale (severity, priority) | score, nearest level, confidence |
| `jev_rank` | which of several candidates answer a question | relevance per candidate, sorted |
| `jev_ask` | anything else, mixed question types | raw System One answers |

Setup: `npx -y @francoischastel/jev-code setup claude codex` registers the
MCP server and drops a skill at `~/.claude/skills/jev/` (or
`~/.agents/skills/jev/` for Codex/Pi/OpenCode) requiring `TYPESAFE_API_KEY`.
Nothing is read from the repo/session automatically — only what the agent
explicitly passes in a call reaches TypeSafe's servers.

## How it could help Chris

Chris's actual workload is heavy on exactly the kind of triage Jev targets —
cheap, high-volume classification decisions currently done by a frontier
model call or by eyeballing:

- **CI/test triage across parallel agent runs.** Given his fleet-of-agents
  setup (many worktrees, PRs, `implement-*` branches), `jev_classify` could
  sort a batch of test failures into flaky/infra vs. real bug before a
  controller agent spends a frontier-model pass on each — this is the exact
  demo jev-code ships (`Triage the failing tests in the last CI run`).
- **Review/verification gating.** His multi-axis-code-review and
  witness-check work (recent commits: "the witness check runs its mutations
  together... its bound refuses to guess") already does calibrated
  yes/no-style verification. `jev_check`/`jev_score` could pre-filter
  findings ("is this finding a real defect or noise?") before a Sonnet/Opus
  reviewer looks at them, cutting reviewer token spend on the easy cases.
- **Batch classification in bulk research/search.** His puzzle-search
  tooling (gridfind, sudokumaker) and any large-corpus filtering (e.g., "does
  this page mention a Hitori/Norinori hybrid") is a `jev_rank`/`jev_classify`
  shape: many candidates, one typed question, needs a probability not prose.
- **Doom-loop / abort-check guard.** `jev-harness`'s "abort-check" pattern
  (catch an agent about to retry an identical failed plan) matches a rule
  already in his memory file about crash/retry discipline — a mechanical
  guard here could reduce reliance on an agent noticing on its own.

Honest caveat: every one of these is a *plausible fit based on the shape of
the tool*, not a validated one. Nothing found demonstrates Jev's accuracy on
Chris's kind of workload (sudoku/code/CI text), only TypeSafe's own general
benchmarks and a toy 100-tool routing demo.

## Costs / risks

- **New and unproven.** Model is six days old at research time; jev-code is
  two days old, 1 star, no independent adoption evidence. Early-access API
  can change or be revoked without notice.
- **Second vendor, second outage mode.** Any workflow built on it needs a
  fallback path that doesn't depend on TypeSafe's API being up (jev-agent.com's
  own docs flag this).
- **Another API key to manage and another place secrets can leak** — worth
  weighing against the value of the triage it buys, especially across many
  parallel agent processes each capable of making Jev calls.
- **Platform**: it's a hosted API called over HTTPS from a Node/Python CLI or
  MCP server — no evidence of WSL-specific issues, but also no evidence
  anyone has run it on WSL; it's untested territory rather than confirmed
  broken.
- **Threshold tuning is on you.** TypeSafe/jev-agent.com explicitly warn: do
  not ship a guessed confidence cutoff, measure it against your own labeled
  traffic — that's real setup work, not drop-in.
- **Context limit**: ~32K token request budget per TypeSafe's docs excerpt —
  fine for triage-sized batches, not for feeding it a full agent transcript
  unsummarized.

## Sources

Primary/official:
- [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) — TypeSafe AI blog, Diogo Almeida (founder), 2026-09-15. Model description, RLCD training method, pricing table, benchmarks, early-access/waitlist status.
- [jev-agent.com/agents](https://jev-agent.com/agents) — "Jev for AI agents" (third-party pattern guide, no author/date listed), agent-loop integration patterns (tool selection, confidence gating, Noul self-checks) and caveats (need an LLM fallback, threshold tuning, ~32K context budget).
- [FrancoisChastel/jev-code](https://github.com/FrancoisChastel/jev-code) — GitHub repo, MIT license, latest commit 2026-09-19, 1 star. Full README: tools, setup for Claude Code/Codex/Pi/OpenCode, security notes, config vars.

Secondary (used only to corroborate, not as primary evidence):
- [PyPI: jev-cli v0.4.1](https://pypi.org/project/jev-cli/), [jev-agent-tool v0.1.0b1](https://pypi.org/project/jev-agent-tool/), [jev-harness v0.1.0](https://pypi.org/project/jev-harness/) — package descriptions, uploaded 2026-09-18 through 2026-09-21.
- [What Is Jev? — LangChain blog](https://www.langchain.com/blog/building-a-harness-with-jev), 2026-09-17, repeats TypeSafe's own speed/cost claims, describes the `TypeSafeClassifier` LangChain integration.
- [Glama: jev-use by shitianfang](https://glama.ai/mcp/servers/shitianfang/jev-use) — another MCP wrapper, TS/JS.

Not independently verified: TypeSafe's own speed/cost/accuracy claims (no
third-party benchmark found); jev-code's actual reliability in daily use
(too new, no adoption signal beyond the README).
