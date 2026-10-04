# Permission rules: precedence, auto mode, and which settings a worktree reads

Sources, read 2026-10-04 on Claude Code 2.1.289:
- Configure permissions, https://code.claude.com/docs/en/permissions
  (sections "Permission system", "Compound commands", "What a Bash rule doesn't
  match", "Settings precedence")
- Auto mode configuration, https://code.claude.com/docs/en/auto-mode-config
  (sections "Add a human checkpoint", "Where the classifier reads
  configuration", "Override the block and allow rules")
- Settings, https://code.claude.com/docs/en/settings ("Where Claude Code keeps
  the local file in a git repository", "Settings precedence")

Written for #1225 (allow-rule precedence, which settings files a worktree
session reads) and #1392 (does an `ask` rule beat a broader `allow`, and does
auto mode prompt or deny it).

## Precedence

- Evaluation order is **deny, then ask, then allow**; the first match decides.
  "The same precedence applies between ask and allow: a matching ask rule
  prompts even when a more specific allow rule also matches the same call."
  So an `ask` entry beats the broader `allow` entries in `flow/claude/settings.json`
  (`Bash(node *)`, `Bash(npm run *)`, `Bash(job-run:*)`); order in the file
  does not matter.
- Across scopes the same order holds: a deny at any scope beats an allow at any
  other, and an `allow` saved to a local file "doesn't outrank an `ask` rule
  from a project or managed file". `permissions.allow` lists merge across
  scopes rather than override.
- Scope precedence for plain keys, highest first: managed, `--settings`,
  project local (`.claude/settings.local.json`), shared project
  (`.claude/settings.json`), user (`~/.claude/settings.json`).

## Auto mode and `ask`

- "Content-scoped ask rules ... are evaluated before the classifier and always
  force a permission prompt, even in auto mode." It is a prompt, not a denial:
  "The classifier cannot auto-approve a matching action." This is the
  mechanism behind the e2e lock in `flow/claude/settings.json` (#1392).
- Deny and ask apply when **any subcommand** of a compound command matches
  (`cd /tmp && git clean -f` still prompts under `Bash(git clean *)`), and a
  leading `timeout`, `time`, `nice`, `nohup`, `stdbuf` or known-safe env
  assignment is stripped before matching.
- A prompt needs someone to answer it. Not read from the docs, inferred: a worker in
  a pane nobody watches would sit `blocked` on it (`drain.py` counts `blocked`
  as stalled), which is the intended stop for the live e2e.
- Narrow allow rules (`Bash(npm test)`) are resolved before the classifier in
  auto mode. Broad ones that grant arbitrary execution (`Bash(*)`, wildcarded
  interpreters such as `Bash(uv run *)`) are suspended while auto mode is
  active, so adding one does nothing for classifier denials. The classifier is
  steered by `autoMode.allow` prose instead.

## What an `ask` or `deny` rule does not match

The rule matches command text as written. It does not match "the same program
invoked in a different form": `/usr/bin/curl` against `Bash(curl *)`,
`sh -c '...'`, `git -C . push` against `Bash(git push *)`. Hence the seven
entries for `e2e.sh` in `permissions.ask`: `./e2e.sh`, `bash e2e.sh`,
`bash ./e2e.sh`, the absolute path with and without `bash`, and the
`.claude/worktrees/*/e2e.sh` copy with and without `bash`. A trailing ` *`
also matches the bare command. Still unmatched, and so unblocked: `sh -c` and
`bash -c './e2e.sh'` (the docs' `sh -c` row). `./e2e.sh` is matched in every
repo, not only twitch-rules-scroller; `ls ~/src/*/e2e.sh` on 2026-10-04 found
only twitch-rules-scroller's. The rule is a prompt-before
guard, not a security boundary.

## `autoMode` placement

- The classifier reads `autoMode` from `~/.claude/settings.json`, managed
  settings and `--settings`. It "doesn't read `autoMode` from project settings
  in `.claude/settings.json` or `.claude/settings.local.json`". A block under
  `permissions.autoMode` is not a documented location in any scope: it was
  silently dead (#1225).
- A list set without `"$defaults"` replaces the built-in list for that section
  and the other three sections are untouched. `soft_deny` in
  `flow/claude/settings.json` has none on purpose (Chris dropped Instruction
  Poisoning from it, see `2026-10-04-auto-mode-self-modification-denials.md`);
  `flow/settings-lint.sh` names that as `OWNED_LISTS`.
- `claude auto-mode config` prints what the classifier actually uses.

## Which settings files a worktree session reads

- **User**: `~/.claude/settings.json`, in every session, worktree or not. On this
  box it is a link to `flow/claude/settings.json`; `flow/install-check.sh`
  fails when it is a plain file.
- **Shared project** (`.claude/settings.json`): read from the session's
  *primary working directory*, which for a worker is its worktree, so the
  worktree's own checked-in copy.
- **Project local** (`.claude/settings.local.json`): "In a worktree, it uses the
  file at the main checkout's root." So a "Yes, and don't ask again" in a worker
  writes one allow rule shared by every worktree of that repo, and a rule that
  starts with `/` or is a relative path anchors at the session's working
  directory, not the repo root. That is the source of the per-worktree
  allow-rule friction in #1225: absolute-path allow rules name one worktree.
  Write such rules in user settings with a `*/.claude/worktrees/*/` glob.
- `allow` rules from a project file wait for workspace trust (keyed on the main
  checkout's root in a worktree); `deny` and `ask` apply at once.

## Compute commands (#1225)

Already in place, so nothing was added: `Bash(job-run:*)` in `permissions.allow`,
and the "Shared-box compute runs" entry in `autoMode.allow`, which covers
`uv run <script>`, `just <recipe>` and `node <script>` under `job-run`. A
broader `Bash(uv run *)` was not added: per the section above it is a
wildcarded interpreter, suspended in auto mode, so it would change nothing.
