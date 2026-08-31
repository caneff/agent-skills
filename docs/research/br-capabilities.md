# `br` (beads_rust) capabilities — verified against primary sources

Research for [#467](https://github.com/caneff/agent-skills/issues/467), child of the tracker-migration map [#466](https://github.com/caneff/agent-skills/issues/466).

Sources: a shallow-then-unshallowed clone of
[Dicklesworthstone/beads_rust](https://github.com/Dicklesworthstone/beads_rust)
(`main`, commit `d2393c9`, 2026-08-31), its `docs/` tree, `Cargo.toml`, `crates.io`'s
API, GitHub's repo/contributors/releases API, and a `br 0.2.22` binary already
installed at `~/.cargo/bin/br` on this machine, run directly for `--help`,
`capabilities --format json`, and `robot-docs guide`. No claim below is taken
from memory or from the ticket's own wording without a source check.

## Install path and current version

- **Not on crates.io.** `curl -s https://crates.io/api/v1/crates/beads_rust`
  returns HTTP 403 (no record), and `docs/INSTALLING.md` never mentions
  publishing there. The three documented install methods are all
  git/source/binary, not a crates.io name:
  1. `cargo install --git https://github.com/Dicklesworthstone/beads_rust.git beads_rust --locked` (docs call this "Recommended")
  2. Build from source (`git clone` + `cargo build --release`)
  3. Pre-built binaries from GitHub Releases
- **The README's actual quick-install is `curl | bash`**, not cargo:
  `curl -fsSL "https://raw.githubusercontent.com/Dicklesworthstone/beads_rust/main/install.sh?$(date +%s)" | bash`
  (`README.md:23`). So the ticket's suspicion was right for the README's own
  front door, even though `docs/INSTALLING.md` separately documents a pinnable
  `cargo install --git ... --locked` path.
- **Pinning is possible**, but only via git ref, not a crates.io semver:
  `cargo install --git <url> beads_rust --locked` can take `--tag vX.Y.Z` or
  `--rev <sha>` (standard cargo behavior for git sources; not spelled out in
  `INSTALLING.md` itself, which shows only the unpinned git URL).
- **Requires Rust nightly** (`docs/INSTALLING.md`: "Rust: Nightly toolchain
  (required for Rust 2024 edition features)"). This is a real adoption cost —
  not just "install cargo."
- **Current version: 0.5.7** (`Cargo.toml` on `main`, matches the newest GitHub
  Release tag `v0.5.7`, published 2026-08-29T20:54:13Z). The binary already on
  this machine is **0.2.22** — three minor versions behind `main`, installed at
  some earlier point. Worth knowing before trusting any local `br --help`
  output as current: I ran it anyway for structural verification (command
  list, `capabilities` shape, `robot-docs` shape), but exact flag sets may have
  moved since 0.2.22.

## Command surface (from `docs/CLI_REFERENCE.md`, cross-checked against the installed binary's `br --help`)

All of the ticket's named operations exist, plus more. Verified subcommand
list from the installed `br --help` matches the documented set (`init`,
`create`, `q`, `list`, `show`, `update`, `close`, `reopen`, `delete`, `ready`,
`scheduler`, `coordination`, `blocked`, `search`, `count`, `stale`, `dep`,
`graph`, `label`, `epic`, `comments`, `defer`/`undefer`, `orphans`, `query`,
`gate`, `capacity`, `sync`, `vcs-status`, `config`, `capabilities`,
`robot-docs`, `serve`, `agents`, `stats`/`status`, `doctor`, `info`, `where`,
`schema`, `version`, `audit`, `history`, `changelog`, `lint`, `upgrade`,
`completions`).

- **`create`**: `-t/--type`, `-p/--priority`, `-d/--description`, `--slug`,
  `-a/--assignee`, `--owner`, `-l/--labels`, `--parent`, `--deps
  type:id,type:id`, `-e/--estimate`, `--due`, `--defer`, `--external-ref`,
  `--ephemeral`, `-s/--status`, `--dry-run`, `--silent`, `-f/--file` (bulk
  import **from Markdown**, not from JSON/CSV/GitHub).
- **`show [IDS]...`**: `--format text|json|toon`.
- **`list`**: rich filtering (`-s`, `-t`, `--assignee`, `--label`/`--label-any`,
  `-p`, `--priority-min/max`, substring filters, `--overdue`, etc.),
  `--format text|json|csv|toon`.
- **`close [IDS]...`**: `-r/--reason`, `--force`, `--suggest-next` (returns
  newly-unblocked issues), `--robot`.
- **`label add|remove|list|list-all|rename`** — plain string labels, no schema
  or enum enforcement built in.
- **`comments add|list`**: `-f/--file`, `--author`, `--message`.
- **`dep add|remove|list|tree|cycles`**: dependency types are `blocks`
  (default), `parent-child`, `discovered-from`, `related`. Cycle checking
  covers `blocks`, `conditional-blocks`, `waits-for`, `parent-child`; `related`
  and `discovered-from` are never cycle-checked. `dep tree` bounds diamond
  expansion by marking repeats `"repeat": true` in JSON rather than
  re-expanding, and epic containment participates in blocking-cycle detection
  (depending on an epic depends on its whole subtree — a descendant of that
  epic can't add a `blocks` edge back into the chain).
- **`ready`**: unblocked + not deferred, default status filter is `open`
  only, widened via `.beads/policy.yaml` (see below). `--sort
  hybrid|priority|oldest`, `--parent`+`--recursive` for scoping to an epic's
  descendants.
- **`blocked`**: issues blocked by other open issues, `--detailed` for full
  blocker info.
- **JSON shapes** (`docs/CLI_REFERENCE.md`, "JSON Output Schemas" section):
  documented shapes for the Issue object (`list`/`show`/`ready`), the
  Dependency object, the Sync Status object, and a structured Error object
  (`error_code`, `message`, `kind`, `recovery_hints`). `br show --json` also
  adds a `rollup` object (furthest-along descendant status + status counts)
  to any issue with parent-child children.

## `.beads/policy.yaml` — routing model

**Labels and status are two separate axes, exactly as the ticket suspected.**
`policy.yaml` governs *status*-based routing only:

- `workflow.status_groups.ready: [open, rework, ...]` widens what `br ready`
  treats as actionable, so a status like `rework` resurfaces through the same
  `br ready --json` call. Default (no config) is `[open]` only.
- `workflow.capacity` adds hard/soft WIP limits and admission gates keyed on
  status transitions (e.g., cap `in_progress` at 3, or require `in_review` to
  drain before admitting more `in_progress`), with scopes (`repository`,
  `actor`, `assignee`, `harness`, `session`, `subtree`) and
  hierarchy-aware counting modes (`all`, `leaf_work`, `roots`, `weighted`)
  so an epic and its children don't each consume a slot.
- **Labels are unstructured strings** (`br label add/remove/list/list-all/
  rename`) with no policy-file integration found anywhere in
  `docs/CLI_REFERENCE.md` or `docs/agent/*.md`. There is no equivalent to
  "a label drives routing" the way `workflow.status_groups` drives `ready`.

So the current GitHub-tracker doc's `ready-for-agent` / `ready-for-human` /
`wayfinder:*` scheme — which conflates a routing signal into a label — would
have to be re-expressed as **br statuses** (via `workflow.statuses` +
`status_groups`) to get native `br ready` filtering, or kept as plain labels
filtered manually with `br list -l <label>` / `--label-any`. br gives no
built-in label-based routing DSL; it only gives status-based routing plus
capacity gates. This is a real design fork for the skills, not a detail.

## `br sync` semantics

Five real modes (`--flush-only`, `--import-only`, `--merge`, `--reconcile`,
`--witness`, plus read-only `--status`, `--reconcile-additive`,
`--migrate-source-repo-path`) — the ticket named all but `--reconcile-additive`
and `--migrate-source-repo-path`, which also exist:

- **`--flush-only`**: export SQLite → `.beads/issues.jsonl`.
- **`--import-only`**: import JSONL → SQLite. `--rebuild` makes JSONL
  authoritative (removes DB-only rows); `--skip-invalid-records` salvages
  valid rows from a JSONL with malformed lines, backing up the original first.
- **`--merge`**: three-way merge using `.beads/beads.base.jsonl` as the common
  ancestor against current SQLite and current JSONL. Conflict resolution:
  `--force-db`, `--force-jsonl`, or `--force` (newer-timestamp wins);
  mutually exclusive.
- **`--reconcile`**: additive, lossless, previewable
  (`--dry-run`); timestamp-newer-wins with tombstone protection; never
  deletes.
- **`--witness`**: deterministic read-only JSONL integrity check.
- **`.beads/beads.base.jsonl` is the merge-base snapshot** — written after a
  successful export or import, used only by `--merge` as the common ancestor
  (`docs/SYNC_SAFETY.md:209`, `:277`; `docs/CLI_REFERENCE.md:1426`).
- **`br sync` never runs git** — no auto-commit, no push/pull. Confirmed both
  in `docs/CLI_REFERENCE.md` ("SAFETY GUARANTEES: NEVER executes git
  commands") and in the installed binary's own `robot-docs guide` output:
  "Normal issue and sync paths never run git. Only an explicit `br vcs-status`
  request runs bounded, read-only Git probes."

## JSONL schema and GitHub import

- The Issue JSON object is documented in full in `docs/CLI_REFERENCE.md`
  ("JSON Output Schemas") and matches a live sample read from this repo's own
  `.beads/issues.jsonl` (`id`, `title`, `description`, `design`,
  `acceptance_criteria`, `notes`, `status`, `priority`, `issue_type`,
  `assignee`, `owner`, timestamps, `close_reason`, `source_system`,
  `dependency_count`, `dependent_count`, etc.) — one JSON object per line.
- **No dedicated GitHub-issues import path exists.** The only bulk-create path
  is `br create -f <file>`, which reads **Markdown**, not JSON, CSV, or a
  `gh issue list --json` dump. There is an `--external-ref <REF>` field
  explicitly documented with the example `gh-123`, meant for exactly this
  kind of cross-reference, but no command converts a GitHub export into
  `issues.jsonl` or into the Markdown bulk-import format automatically. A
  migration would need a script: `gh issue list --json ... ` → either
  hand-write `.jsonl` matching the documented Issue schema and `sync
  --import-only` it, or render one Markdown block per issue for `br create
  -f`. Neither path is provided by the tool itself.

## Parent/child (epic) modelling

Yes — first-class, not a label convention:

- `br create --parent <ID>` creates a parent-child dependency directly.
- `br update <ID> --parent <ID>` reparents (empty string removes).
- `br dep add <ISSUE> <DEPENDS_ON> --type parent-child` is the general form.
- `br epic status [--eligible-only]` shows child progress and eligibility;
  `br epic close-eligible` atomically closes epics whose children are done.
- `br show --json` on a parent adds a `rollup` object: furthest-along
  non-terminal descendant status, plus a per-status descendant count.
- `br ready --parent <ID> [--recursive]` scopes the ready set to one epic's
  (optionally full-subtree) children.
- Epic containment is cycle-checked as described above (depend-on-epic =
  depend-on-all-descendants).

This covers what the map calls "a map owning child tickets the way GitHub
sub-issues do" — arguably more capability than GitHub sub-issues have (rollup
status, capacity-aware counting that treats an epic as non-executing work via
`counting.weights.types.epic: 0`).

## `br robot-docs` and `br capabilities --format json`

Ran both directly against the installed `br 0.2.22` binary rather than trusting
the docs description:

- **`br capabilities --format json`** returns a real, structured self-description:
  `tool`, `version`, `contract_version` (`"br.capabilities.v1"`), a `features`
  array (e.g. `local_first_issue_tracking`, `agent_machine_output`,
  `schema_export`, `coordination_diagnostics`, `mcp_stdio_optional`), and a
  `commands` array — one entry per subcommand with `name`, `summary`,
  `operation` (`read`/`write`/`mixed`/`unknown`), `workspace`
  (`required`/`optional`/`none`/`unknown`), `machine_output` formats, and
  `examples`. Passing `--command <path>` (documented, not independently run
  here) adds full flag/positional/example detail for one command. This is
  genuinely enough for an agent to discover the command surface without a
  hand-written skill doc, **for command existence and shape** — it does not
  by itself teach the policy semantics (status groups, capacity, epic
  cycle rules) documented in prose in `CLI_REFERENCE.md`.
- **`br robot-docs guide`** prints a short (confirmed: well under 80 lines,
  matching the doc's claim) fixed handbook: purpose, machine-output
  conventions, a "start of session" command sequence (`br capabilities
  --format json`, `br ready --json`, `br coordination status --json`, `br
  show <id> --json`), how to find work (`br ready --json`, and explicitly:
  "Don't hand-roll status filters ... call `br ready --json` and let project
  policy define readiness"), how to claim (`br update <id> --claim --actor
  ...`), how to complete (`br close ... --reason ...` then `br sync
  --flush-only`), and safety notes (never auto-commits, schema migrations are
  never implicit). This is a genuinely useful, tool-authored onboarding doc —
  short enough to paste into an agent's context directly instead of
  maintaining a parallel hand-written one.

## Maintenance signal

- **Extremely young repo, extremely active, effectively one committer.**
  Full unshallowed history: **50 commits total**, spanning **2026-08-27 to
  2026-08-30** — four days old at the time of this research (2026-08-31).
  48 of 50 commits are by "Jeff Emanuel", 2 by "Dicklesworthstone"; GitHub's
  own profile API confirms `Dicklesworthstone`'s display name **is** "Jeff
  Emanuel" — same person, so this is a single-author project by that
  measure.
- GitHub's contributors API confirms this at the whole-repo level (not just
  this shallow window): `Dicklesworthstone` — 2,630 contributions;
  `dependabot[bot]` — 9; no other human contributor.
- **7 open issues**, 119 forks, 1,072 stargazers (`gh api
  repos/.../{issues_count,forks,stargazers_count}`, live at research time).
- Commit cadence in the visible window is very high (roughly a dozen commits
  a day) — a strong contrast between "actively developed" and "bus-factor of
  one." Both are true simultaneously and both matter for the #466 decision.

## What's still uncertain / not independently verified here

- The exact flag surface at **current `main` (0.5.7)** vs. the installed
  **0.2.22** binary — I read `main`'s `docs/CLI_REFERENCE.md` (which should
  track `main`) but only *ran* the older binary. Command names matched; I did
  not diff every flag between versions.
- Whether `cargo install --git ... --tag vX.Y.Z` actually resolves and builds
  cleanly under nightly on this machine — not attempted (would require a
  nightly toolchain build here, which the environment doesn't have compiled
  yet, and was out of scope for a docs-and-structure verification pass).
- Whether `br schema all --format json` / `br schema issue-details` (the
  formally-versioned schema surface, distinct from `capabilities`) is present
  in 0.2.22 — `docs/agent/SCHEMA.md` warns older binaries may lack `br
  schema` entirely ("unrecognized subcommand"); not tested against the local
  binary.
