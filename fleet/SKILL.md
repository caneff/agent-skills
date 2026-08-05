---
name: fleet
description: Spawn one standing background agent per directory listed in a central fleet file, so the agent overview is prepopulated with an agent parked in each subdirectory of interest. Use when the user wants to "start my fleet", "open agents in my dirs", "spin up my agents", or add/remove directories from the fleet list.
---

Spin up one background agent per directory the user cares about, reading the directory list from a central file so the user (or this skill) can edit it any time.

## The fleet file

`~/.claude/fleet-dirs.txt` — one directory path per line. `~` and env vars are allowed; blank lines and lines starting with `#` are ignored.

If the file does not exist, create it with a header comment and nothing else, then tell the user it's empty and how to add dirs (below). Do **not** spawn anything on an empty list.

Example:

```
# fleet-dirs.txt — one directory per line. Blank lines and # comments ignored.
~/src/gridfind
~/.agents/skills
~/src/iss-stuff/quad-rank
```

## Arguments

Dispatch on the skill's argument:

- **(no args)** → **spawn the fleet** (main flow below).
- **`list`** → print the current file contents (expanded to absolute paths), one per line, marking any path that doesn't exist. Spawn nothing.
- **`add <path>`** → append `<path>` to the file if not already present (compare by resolved absolute path), then print the updated list. Spawn nothing.
- **`remove <path>`** / **`rm <path>`** → delete the line whose resolved path matches `<path>`; warn if no match. Spawn nothing.
- **`edit`** → print the file's path and tell the user they can edit it directly (`! $EDITOR ~/.claude/fleet-dirs.txt`). Spawn nothing.

## Spawn the fleet

1. Read `~/.claude/fleet-dirs.txt`. Drop blank/`#` lines. Expand `~` and env vars to absolute paths.
2. For each path, check it exists and is a directory. Collect the missing ones; **skip** them (don't spawn) and list them in the final report.
3. Derive a name for each agent from the directory's basename, sanitized to match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` (replace any other character with `-`). On a name collision, suffix with the parent directory name, then `-2`, `-3`, … until unique.
4. Spawn **all** agents in a **single message** (parallel tool calls), one `Agent` call each, with:
   - `subagent_type: general-purpose`
   - `name:` the derived name
   - `run_in_background: true` (named + background = a standing teammate that parks idle and waits for `SendMessage`)
   - `prompt:` the standing-agent prompt below, with `<DIR>` filled in.

Standing-agent prompt:

```
You are the standing agent for <DIR>. Treat <DIR> as your root: start with `cd <DIR>` and run every command from there.

Do a quick orientation, then STOP and wait:
1. `pwd` to confirm, `ls` the top level, and if it's a git repo `git status -s` and the current branch.
2. In 2-3 lines, report what this directory is and anything notable (dirty tree, an obvious current task, a README one-liner).
3. Then park — take no further action until I message you with a task.

Do not modify anything during orientation. Keep the report short.
```

5. Report the roster back to the user: a table of `name → directory`, note any skipped (missing) directories, and remind them they can address any agent later via `SendMessage` (or from the agent overview), and re-run this skill after editing the fleet file to change the lineup.

## Notes

- The fleet file is plain text on purpose — the user edits it by hand or this skill edits it via `add`/`remove`. No config format, no schema.
- Re-running the skill spawns a fresh set; it does not deduplicate against agents already running from a previous run. If the user wants to change the lineup, they edit the file (or use `add`/`remove`) and re-run.
