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

- **(no args)** → **spawn the fleet** (main flow below). By default the directory list comes from your VSCode workspace, not the fleet file.
- **`list`** → print the current file contents (expanded to absolute paths), one per line, marking any path that doesn't exist. Spawn nothing.
- **`add <path>`** → append `<path>` to the file if not already present (compare by resolved absolute path), then print the updated list. Spawn nothing.
- **`remove <path>`** / **`rm <path>`** → delete the line whose resolved path matches `<path>`; warn if no match. Spawn nothing.
- **`edit`** → print the file's path and tell the user they can edit it directly (`! $EDITOR ~/.claude/fleet-dirs.txt`). Spawn nothing.
- **`workspace [<file>]`** → import folders from a VSCode `.code-workspace` file into the fleet file, then print the updated list. Spawn nothing. See below.

## Spawn the fleet

1. Get the directory list. **Default to the VSCode workspace:** glob `~/src/*.code-workspace` — exactly one → resolve its folders (see the `workspace` section below) and use those; several → list them and ask which; none → fall back to `~/.claude/fleet-dirs.txt`. Reading a workspace this way does **not** write to the fleet file — it's a live source. (Use `workspace` explicitly if you want the dirs saved to the fleet file instead.) Whichever source: drop blank/`#` lines, expand `~` and env vars to absolute paths.
2. For each path, check it exists and is a directory. Collect the missing ones; **skip** them (don't spawn) and list them in the final report.
3. Derive a name for each agent from the directory's basename, sanitized to match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` (replace any other character with `-`). On a name collision, suffix with the parent directory name, then `-2`, `-3`, … until unique.
4. List the currently running background agents (use `TaskList`, or the agent overview) and collect their names. For each directory whose derived name matches a running agent, **skip** it — don't spawn a duplicate — and record it as "already running" for the report.
5. Spawn **all** remaining agents in a **single message** (parallel tool calls), one `Agent` call each, with:
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

6. Report the roster back to the user: a table of `name → directory`. List skipped directories in two groups — **missing** (path doesn't exist) and **already running** (an agent with that name is already up). Remind them they can address any agent later via `SendMessage` (or from the agent overview), and re-run this skill after editing the fleet file to change the lineup.

## Import from a VSCode workspace (`workspace` arg)

A `.code-workspace` file is JSON with a `folders` array; each `folders[].path` is **relative to the workspace file's own directory**. Import them:

1. Resolve the file. If `<file>` given, use it. Else glob `~/src/*.code-workspace`: exactly one → use it; several → list them and ask which; none → tell the user to pass a path.
2. Extract and resolve each folder path against the file's directory. One line does it:
   ```
   WS=~/src/uberworkspace.code-workspace
   jq -r '.folders[].path' "$WS" | while read p; do realpath -m "$(dirname "$WS")/$p"; done
   ```
3. Append each resolved path to `~/.claude/fleet-dirs.txt` if not already present (compare by resolved absolute path), same as `add`. Then print the updated list.

This does not spawn the fleet — run the skill with no args afterward to do that. It also does not auto-track the *currently focused* VSCode window; it imports whatever workspace file you point at.

## Notes

- The fleet file is plain text on purpose — the user edits it by hand or this skill edits it via `add`/`remove`. No config format, no schema.
- Re-running the skill skips any directory whose derived agent name is already running, so it won't spawn duplicates on top of a previous run — only directories without a live agent get a fresh spawn. To change the lineup, edit the file (or use `add`/`remove`) and re-run.
