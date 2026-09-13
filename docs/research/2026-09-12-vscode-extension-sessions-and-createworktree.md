# VS Code extension: sessions sidebar and `createWorktree`

Research ticket: [caneff/agent-skills#701](https://github.com/caneff/agent-skills/issues/701) (wayfinder map #700, the Orca exit).
Date: 2026-09-12.

## Versions under test

| Thing | Version |
| --- | --- |
| VS Code (remote server, WSL2) | 1.137.0, commit `645f29cc3176500b4b5762ba887cf2a7f0ffdf2c` |
| `anthropic.claude-code` extension | 2.1.269 (`code --list-extensions --show-versions` → `anthropic.claude-code@2.1.269`) |
| Extension `engines.vscode` | `^1.94.0` (`package.json`) |

Extension root, cited throughout as `EXT`:
`/home/caneff/.vscode-server/extensions/anthropic.claude-code-2.1.269-linux-x64`

`EXT/extension.js` is a 3.4 MB bundle with very long lines, so code citations give
both the minified symbol name and a `line:col` position. Symbols are stable within
this build only.

## Summary of the four answers

1. Yes. The sidebar lists any session whose transcript `.jsonl` sits in the
   workspace folder's project directory under `~/.claude/projects`, regardless of who
   started it. A terminal-started `claude` is additionally flagged "live elsewhere"
   with holder `terminal` by a separate registry of `~/.claude/sessions/<pid>.json`
   files. Nothing about the sidebar list depends on the extension having launched it.
2. `claude-vscode.createWorktree` creates `<repoRoot>/.claude/worktrees/<name>` on a
   new branch `worktree-<name>` based on `origin/<defaultBranch>`, then opens that
   folder in a new VS Code window. It is **not** invocable from the CLI, and in
   2.1.269 it is not invocable at all: the command is declared in `package.json` but
   never registered, and its palette gate context key is never set. The only live
   path is the webview's `create_worktree` message.
3. Yes, through the URI handler:
   `vscode://anthropic.claude-code/open?prompt=<urlencoded>&session=<id>`. The prompt
   is pre-filled, not submitted. It opens a session tab in the primary editor. From a
   VS Code integrated terminal, `code --openExternal "<uri>"` reaches it.
4. Two separate signals. For sessions the extension hosts, the webview reports
   `idle` / `running` / `waiting_input` and the tab icon swaps to a pending or done
   badge. For sessions running anywhere else, including a shell terminal, the live
   registry's `status` field (`busy` / `shell` / `idle` / `waiting`) is mapped to
   `running` / `waiting` / `idle` and rendered as "Open in a terminal — awaiting
   input".

---

## Q1. Which sessions does the sidebar list, and what makes one appear?

### What the sidebar is

Two activity-bar containers are contributed. `claude-sessions-sidebar` holds the
webview view `claudeVSCodeSessionsList`, gated on the context key
`claude-vscode.sessionsListEnabled` (`EXT/package.json`,
`contributes.viewsContainers.activitybar` and `contributes.views`). That key is set
unconditionally to `true` at activation (`EXT/extension.js:1056:5815`, the
`setContext("claude-vscode.sessionsListEnabled",!0)` call inside `Fd0`), so the
sessions list is always present. The docs agree: "click the Spark icon in the left
sidebar to open the sessions list ... This icon is always visible in the Activity
Bar." (https://code.claude.com/docs/en/vs-code, "Open the extension").

### The list is built from transcript files on disk

The webview asks for `list_sessions_request`; the host answers from `listSessions` →
`readSessionList` → `buildSessionList` (`EXT/extension.js:473:74695`). The query is:

```
{dir: this.cwd, includeWorktrees: false, includeProgrammatic: this.includeProgrammaticSessions}
```

That reaches `jD` (`EXT/extension.js:391:322`), which `readdir`s the project
directory and keeps every entry that ends in `.jsonl` whose stem parses as a UUID,
stat-ing each for its mtime. The project directory is
`join(configDir, "projects", encode(cwd))`, where `configDir` honours
`CLAUDE_CONFIG_DIR` and otherwise is `~/.claude` (`q1`/`SI4`,
`EXT/extension.js:178:39...`). Rows are then sorted by mtime, newest first (`KA0`,
`EXT/extension.js:389`).

There is **no process scan** in this path. The extension does track PIDs it spawned
itself (`trackClaudeProcess` / `getClaudeProcesses`, `EXT/extension.js:473:76047`), but
only to exclude its own processes from the live registry described below, never to
decide what is listed.

### What is filtered out

Four exclusions, all read out of the transcript file:

| Filter | Where | Effect |
| --- | --- | --- |
| `entrypoint` in `{sdk-cli, sdk-ts, sdk-py}`, or `sessionKind` in `{daemon, daemon-worker}` | `Fv`, `EXT/extension.js:98:207`; set `_D0` defined on the same line | dropped, because the VS Code host sets `includeProgrammaticSessions = !1` (`EXT/extension.js:988:1439`) |
| `"isSidechain":true` on the first line | `Te`, `EXT/extension.js:389:1303` | subagent transcripts dropped |
| a `continuedInSessionId` pointing at another live transcript | `ik$` + `nk$`, `EXT/extension.js:389` | superseded sessions dropped |
| recorded `cwd` resolves to a different checkout than the project path | `ak$`, `EXT/extension.js:391` | relocated sessions dropped |

Because the query passes the workspace `cwd` and `includeWorktrees: false`, only
sessions whose cwd **is** the opened workspace folder are listed. A `claude` started
in a subdirectory writes to a different encoded project directory and does not
appear. (`_3`, `EXT/extension.js:98`, widens only to truncated-prefix spellings of
the same path, not to children.)

### Local probe

This research session is itself a `claude` process in a VS Code integrated terminal
that the extension did not create. Its transcript is
`/home/caneff/.claude/projects/-home-caneff--agents-skills/682976d5-dd36-424b-bef7-acb395dc7128.jsonl`,
and `grep -o '"entrypoint":"[^"]*"'` on it returns `"entrypoint":"cli"`. `cli` is not
in the programmatic set, the transcript is not a sidechain, and its cwd is exactly
`/home/caneff/.agents/skills`. So with that folder open in VS Code, this session
would be listed.

### The separate "live elsewhere" registry

A second mechanism detects running sessions by process, and it is what distinguishes
a terminal session from a stale transcript. Class `L$$`
(`EXT/extension.js:473:2253`) reads `<configDir>/sessions/*.json` — the directory
name comes from `be($) = join($, "sessions")` (`EXT/extension.js:391:13955`) — keeps
files named `<pid>.json`, and validates each record with `Gf$`
(`EXT/extension.js:391:14473`). Fields used: `cwd`, `startedAt`, `procStart` /
`procStartFt`, `kind`, `sessionId`, `status`, `entrypoint`, `pidDomain`.

A record counts as live only if `process.kill(pid, 0)` succeeds and the recorded
process-start token still matches, which rejects PID reuse (`isLive`, `gv`,
`EXT/extension.js:391` and `473`). Records belonging to the extension's own child
processes are skipped. `startLiveRegistry(cwd)` seeds `projectDirs` with the
workspace folder (`EXT/extension.js:996:50819`), and the directory is watched for changes
plus rescanned on a timer (`startLiveRegistry`, `EXT/extension.js:996:50819`).

Each surviving record is reduced to `{sessionId, holder, activity, sameProject}`:

- `holder` from `Yw0` (`EXT/extension.js:473:1613`): `entrypoint` `cli` → `terminal`,
  `claude-vscode` → `vscode`, `claude-desktop` / `claude-desktop-3p` → `desktop`,
  anything else or a non-`interactive` `kind` → `other`.
- `activity` from `zw0` (`EXT/extension.js:473:1943`): `busy` → `running`,
  `waiting` → `waiting`, everything else → `idle`.
- `sameProject`: record `cwd` is one of the registered project dirs.

The webview reacts to exactly this: it re-lists sessions when it sees a record with
`holder === "terminal" && sameProject` whose session it does not already have
(`EXT/webview/index.js:2179:41633`).

### Local probe of the registry

```
$ ls /home/caneff/.claude/sessions/ | head -1
1023054.json
$ grep -ho '"status":"[a-z]*"' /home/caneff/.claude/sessions/*.json | sort | uniq -c
      8 "status":"busy"
     86 "status":"idle"
      5 "status":"shell"
      2 "status":"waiting"
$ grep -ho '"entrypoint":"[a-z-]*"' /home/caneff/.claude/sessions/*.json | sort | uniq -c
      4 "entrypoint":"claude-vscode"
    101 "entrypoint":"cli"
     19 "entrypoint":"sdk-cli"
```

The record for this session, at the time of writing:

```json
{"pid":1922416,"sessionId":"682976d5-dd36-424b-bef7-acb395dc7128",
 "cwd":"/home/caneff/.agents/skills","kind":"interactive","entrypoint":"cli",
 "status":"busy","pidDomain":"linux:...:pid:[4026532221]",
 "messagingSocketPath":"/run/user/1000/cc-socks/1922416.sock"}
```

`holder` = `terminal`, `activity` = `running`, `sameProject` = true for the
`/home/caneff/.agents/skills` workspace.

### Answer

A session appears because a **transcript file** exists in the workspace folder's
project directory, not because of a process and not because the extension launched
it. The process is a second, independent signal that only decorates a row with
liveness, holder, and activity. A `claude` started in any terminal, integrated or
not, qualifies on both counts as long as its cwd is the opened workspace folder and
its entrypoint is `cli`.

**Confidence: fact** for the discovery mechanism, the filters, the registry path and
its fields — read directly from the 2.1.269 bundle and confirmed by probing
`~/.claude/projects` and `~/.claude/sessions` on this machine. **Inference** for the
end-to-end claim that the row renders in a real window, since that was not observed
in a GUI; every code path feeding it was read.

---

## Q2. What `claude-vscode.createWorktree` does

### The implementation

`createWorktree(name)` on the host (`EXT/extension.js:994:5358`):

```js
async createWorktree($){ bi($); let Q=await ki(this.cwd);
  if(!Q) throw Error("Not inside a git repository"); await uO$(this.context,Q,$) }
```

- `bi` → `Pi` validates the name (`EXT/extension.js:178:44391`): non-empty, ≤ 64
  chars, matches `/^[a-zA-Z0-9._-]+$/`, not `.` / `..`, no `..` substring, no
  trailing `.` or `.lock`, not `.git`.
- `ki` resolves the repository root from `git rev-parse --git-common-dir`, with
  fallbacks for bare repos and a symlink-escape check (`EXT/extension.js:178`).
- `uO$` (`EXT/extension.js:179:5892`) calls `gO$`, records the result in
  `globalState` under `pendingPrimaryEditorPath`, then runs
  `vscode.openFolder(<worktreePath>, {forceNewWindow:true})`.

`gO$` (`EXT/extension.js:179:5423`) is the creation itself:

| Step | Command / value |
| --- | --- |
| Target path | `join(repoRoot, ".claude", "worktrees", name)` — `tO`, `EXT/extension.js:178:44929` |
| Branch name | `` `worktree-${name}` `` |
| Symlink guard | `.claude`, `.claude/worktrees`, and the target must not be symlinks — `IO$`, refuses with a message about a repository-committed symlink redirecting creation outside the repo |
| Reuse | if `git rev-parse --show-toplevel` in the target already resolves to the target, it returns that path unchanged |
| Default branch | `git symbolic-ref refs/remotes/origin/HEAD`, else first of `origin/main`, `origin/master` that verifies, else literal `main` — `oI4`, `EXT/extension.js:179` |
| Base ref | `git fetch --upload-pack=git-upload-pack origin <defaultBranch>`; on success `origin/<defaultBranch>`, on failure `HEAD` |
| Before creating | `git worktree prune`, then **`git branch -D worktree-<name>`** |
| Create | `git worktree add -b worktree-<name> <path> <baseRef>` |
| After | `nI4` verifies `git worktree list` really put the checkout at the expected path and fails loudly otherwise |

Timeouts: 5 s for the read-only `rev-parse` probes, 600 s for fetch, prune, branch
delete, and `worktree add` (`jQ=5000, DV=600000`, `EXT/extension.js:178`).

Note the `git branch -D worktree-<name>` before creation. Reusing a name discards an
existing branch of that name unconditionally, with its exit code ignored.

The path and branch convention matches the CLI's documented `--worktree`: "By
default, the worktree is created under `.claude/worktrees/<name>/` at your repository
root, on a new branch named `worktree-<name>`"
(https://code.claude.com/docs/en/worktrees, "Start Claude in a worktree"). The base
also matches the documented `"fresh"` default, "the repository's default branch on
the remote, usually `main`" (same page, "Choose the base branch"). The extension
reimplements the convention in-process rather than shelling out to `claude
--worktree`, so CLI-side behaviour such as `.worktreeinclude` copying and
`worktree.baseRef` is **not** applied by this command path.

### Can it be invoked from the CLI, or from the palette?

No, and in 2.1.269 not from the UI command system either.

- The command is declared: `{"command":"claude-vscode.createWorktree","title":"Claude
  Code: Create Worktree"}` in `EXT/package.json` `contributes.commands`.
- It is never registered. `grep -c 'claude-vscode\.createWorktree' EXT/extension.js`
  → `0`. All 28 `registerCommand(` call sites in the bundle use literal strings, and
  that id is not among them. Calling it would fail with
  `command 'claude-vscode.createWorktree' not found`.
- Its palette entry is gated on `claude-vscode.createWorktreeEnabled`
  (`EXT/package.json` `contributes.menus.commandPalette`), and
  `grep -c createWorktreeEnabled EXT/extension.js` → `0`. The sibling keys
  `sessionsListEnabled` and `primaryEditorEnabled` are both set at activation; this
  one is not. So it is hidden from the palette as well.
- The documented VS Code command table does not list Create Worktree at all
  (https://code.claude.com/docs/en/vs-code, "VS Code commands and shortcuts").

The only reachable path is the webview: the chat UI calls
`createWorktree(name)` → `sendRequest({type:"create_worktree", name})`
(`EXT/webview/index.js:1468:20402`), and the
host handles `case "create_worktree"` in `processRequest`
(`EXT/extension.js:473:70166`).

There is also no CLI surface for arbitrary commands. `code --help` on this build
lists no `--command` flag (full output captured below in Q3), and VS Code has no such
flag; there is no way to drive a registered extension command from a shell.

### Answer

`.claude/worktrees/<name>`, branch `worktree-<name>`, base `origin/<default>` with
`HEAD` as fallback, new window afterwards, and an unconditional `git branch -D` of
the target branch name first. Not CLI-invocable. In 2.1.269 not palette-invocable
either, because the command is unregistered and its gate key is never set; webview
only.

**Confidence: fact.** Path, branch, base, fetch, and the branch delete are read
straight from `gO$`. The non-registration is a fact from two greps returning zero on
the shipped bundle plus an enumeration of all `registerCommand` literals. Not
verified by actually invoking the command, which would have opened a GUI window and
mutated a repository, both out of scope for this ticket.

---

## Q3. Launching from the CLI with a prefilled prompt

### The URI handler

`EXT/extension.js:1056:10910` registers a URI handler:

```js
registerUriHandler({handleUri(O){ let D=new URLSearchParams(O.query);
  switch(O.path){
    case"/install-plugin": ... ;
    case"/open":{ let j=D.get("session")??void 0, R=D.get("prompt")??void 0;
      if(j!==void 0&&!cq(j))return;
      h$.commands.executeCommand("claude-vscode.primaryEditor.open",j,R); return }
  }}})
```

`claude-vscode.primaryEditor.open(sessionId, initialPrompt)` calls
`createPanel(sessionId, initialPrompt, ...)` (`EXT/extension.js:996:53...`), which creates
the `claudeVSCodePanel` webview and delivers the prompt through
`notifyActivateSession(sessionId, initialPrompt)` as
`{type:"activate_session", sessionId, initialPrompt}` (`EXT/extension.js:988:4...`).

`createPanel` also handles the already-open case: if the session has a panel it
reveals it and, when a prompt was supplied, shows "Session is already open. Your
prompt was not applied — enter it manually." So a prompt only lands on a fresh panel.

The docs state the contract exactly:

> The extension registers a URI handler at `vscode://anthropic.claude-code/open`.
> ... `prompt` — Text to pre-fill in the prompt box. Must be URL-encoded. The prompt
> is pre-filled but not submitted automatically. ... `session` — A session ID to
> resume instead of starting a new conversation. The session must belong to the
> workspace currently open in VS Code.

(https://code.claude.com/docs/en/vs-code, "Launch a VS Code tab from other tools".)
Example given there: `vscode://anthropic.claude-code/open?prompt=review%20my%20changes`.

### Reaching the handler from a shell

The documented openers are OS URL openers, `xdg-open` on Linux. Inside this WSL
remote setup there is a second route. `code` on PATH resolves to
`/home/caneff/.vscode-server/bin/645f29cc.../bin/remote-cli/code`, and its help lists
no `--command` and no `--open-url`:

```
$ code --help | grep -iE 'open-url|--command'
(no matches)
```

The remote CLI does accept an undocumented `--openExternal`, gated on being run from
inside a VS Code integrated terminal:

```js
// out/server-cli.js
let n={...Ve, gitCredential:{type:"string"}, openExternal:{type:"boolean"}};
mt && (n.openExternal={type:"boolean"});
...
if(mt && s.openExternal){ await L1(s._, a); return }
async function L1(t,e){ ... qt({type:"openExternal", uris:n}, e) }
...
mt = process.env.VSCODE_IPC_HOOK_CLI
```

`VSCODE_IPC_HOOK_CLI` is set in this terminal, so `--openExternal` is available here.
`L1` accepts any `scheme://...` argument, so
`code --openExternal "vscode://anthropic.claude-code/open?prompt=..."` should route
the URI into the focused window's handler.

### Session tabs for a CLI-launched session

Yes, and this is the same mechanism the sidebar uses. Passing `session=<uuid>` opens
the primary-editor tab on that session, provided the id passes `cq` (a UUID check)
and the session belongs to the open workspace. Opening a row from the sidebar goes
through `claude-vscode.editor.open` / `primaryEditor.open` with the same session id,
so a session started in a terminal and then opened this way gets an ordinary session
tab.

### Answer

`vscode://anthropic.claude-code/open?prompt=<urlencoded>[&session=<uuid>]`, opened
with `xdg-open` or, from a VS Code integrated terminal, `code --openExternal`. The
prompt is pre-filled and not submitted. Session tabs open for any session in the
workspace, including ones the extension did not start.

**Confidence: fact** for the handler, its two parameters, the prefill-not-submit
behaviour, the absence of `--command`/`--open-url` from `code --help`, and the
presence of `--openExternal` in the server CLI's option table — all read from the
shipped code and the official page. **Inference** for `code --openExternal
"vscode://..."` actually opening the tab: the code path is complete and the gating
env var is set, but the command was not run, because doing so would open a GUI panel
and the ticket forbids that.

---

## Q4. Idle and permission-waiting signals

Two independent signals, for two different kinds of session.

### Sessions the extension hosts

The panel webview computes a state from its own session object and reports it with
`update_session_state` (`EXT/webview/index.js:1629:90235`):

```js
let H=(z.permissionRequests.value.length??0)>0, W=z.busy.value, B=z.backgroundTaskIds.value.size>0;
if(H) K="waiting_input"; else if(W||B) K="running"; else K="idle";
```

The allowed states are `["idle","running","waiting_input"]` (`Q8$`,
`EXT/extension.js:113:56467`), validated host-side by the zod schema `ss$` with fields
`{sessionId, state, title?, isPanelInitial?, panelNoLongerHosts?, isFarewell?,
idConfirmed?}` (`EXT/extension.js:177:50003`). The host stores them in `sessionStates` and
broadcasts to every surface (`updateSessionState` / `broadcastSessionStates`,
`EXT/extension.js:996:46...`).

The editor tab icon is a second rendering of the same thing. `rename_tab` carries
`hasPendingPermissions` and `hasUnseenCompletion` (`EXT/extension.js:988:7973`), and `ml$`
(`EXT/extension.js:482:15275`) picks the icon:

```js
if($?.hasPendingPermissions) return "pending";
if((unread ?? $?.hasUnseenCompletion===!0) && Q?.state!=="running") return "done";
return "plain";
// {pending:"claude-logo-pending.svg", done:"claude-logo-done.svg", plain:"claude-logo.svg"}
```

All three files exist in `EXT/resources/`. The docs describe the visible result: "a
small colored dot on the spark icon indicates status: blue means a permission request
is pending, orange means Claude finished while the tab was hidden."
(https://code.claude.com/docs/en/vs-code, "Run multiple conversations".)

### Sessions running anywhere else, terminal included

For a session the extension does not host, the signal is the live registry's
`status` field. Valid values are `["busy","shell","idle","waiting"]` (`TA0`,
`EXT/extension.js:391:14246`), written by the CLI into
`~/.claude/sessions/<pid>.json`. `zw0` (`EXT/extension.js:473:1943`) maps
`busy → running`, `waiting → waiting`, and both `shell` and `idle` → `idle`. When
several records share a session id, the highest-ranked activity wins, ordered
`{idle:0, running:1, waiting:2}` (`Rg$`, `EXT/extension.js:473:2109`).

The sessions-list row combines both sources (`EXT/webview/index.js:2178:11668`):

```js
function lH0($,J,Z,Y,X){            // isOpen, busy, pendingInput, isUnread, liveActivity
  if(!$&&X===void 0) return Y?"unread":void 0;
  let Q=$?Z:X==="waiting", G=$?J:X==="running";
  if(Q) return "waiting"; if(G) return "running"; return Y?"unread":"idle" }

function dH0($,J){                  // openState, holder
  if($==="unread") return "Unread";
  let Z = J===void 0 ? "Open in a tab"
        : J==="terminal" ? "Open in a terminal"
        : J==="vscode" ? "Open in another VS Code window"
        : J==="desktop" ? "Open in Claude Desktop"
        : "Open in another Claude process";
  return $==="waiting" ? `${Z} — awaiting input`
       : $==="running" ? `${Z} — running` : Z }
```

So a terminal session blocked on a permission prompt reads "Open in a terminal —
awaiting input", and a busy one reads "— running". For a session the extension hosts,
the same row uses the panel's own `busy` / `pendingInput`.

There is a third, panel-local string for the multi-agent card view: "Waiting for your
permission to run `<toolName>`. Answer it in the session's permission card."
(`EXT/webview/index.js:2152:18461`).

Two records in the local registry currently carry `"status":"waiting"`, so the value
is produced in practice, not just declared.

### Answer

Host-side, `waiting_input` plus a `claude-logo-pending.svg` tab badge for a pending
permission request, and `idle` / `running` otherwise. Registry-side, `status:
"waiting"` in `~/.claude/sessions/<pid>.json` surfaced as activity `waiting` and the
label "— awaiting input", with `busy` → running and `shell` / `idle` → idle. A
terminal session's permission prompt is therefore visible to the extension, but only
through the registry file, and only as the coarse `waiting` value with no tool name.

**Confidence: fact** for the state enums, the mapping functions, the icon selection,
the label strings, and the presence of `waiting` records on disk. **Inference** for
the claim that the CLI writes `status:"waiting"` specifically when a permission
prompt is open: that write happens CLI-side, outside the extension bundle, and was
not traced. The extension's own label for the value is "awaiting input", which covers
permission prompts and any other blocking question alike.

---

## Things worth knowing for the dispatch design

1. **Transcript presence, not process presence, decides listing.** Writing a session
   into the right project directory is sufficient for a row; the live registry only
   decorates it.
2. **The list is keyed to the exact workspace folder.** `includeWorktrees: false` and
   cwd-based project-directory encoding mean a session started in a subdirectory or in
   a worktree does not show in the parent workspace's list.
3. **`createWorktree` is dead code from any scriptable angle in 2.1.269.** Anything
   depending on it must go through `claude --worktree` or `git worktree add` directly.
   It also `git branch -D`s the target branch name before creating, which is
   destructive on name reuse.
4. **The URI handler is the only scriptable launch surface**, and it pre-fills without
   submitting, so a dispatched prompt still needs a human keystroke.
5. **`~/.claude/sessions/<pid>.json` is a useful read for any dispatcher**, not just
   the extension: `sessionId`, `cwd`, `status`, `entrypoint`, `kind`, and a
   `messagingSocketPath` per live session, with PID-reuse protection via the recorded
   process-start token.

## Sources

- `EXT/package.json` — contributed commands, views, view containers, palette gates.
- `EXT/extension.js` (2.1.269) — symbols cited inline: `Fd0`, `buildSessionList`,
  `jD`, `_3`, `Fv`, `Te`, `ak$`, `ik$`, `nk$`, `KA0`, `L$$`, `be`, `Gf$`, `TA0`,
  `zw0`, `Yw0`, `Rg$`, `createWorktree`, `gO$`, `uO$`, `tO`, `Pi`, `bi`, `ki`, `oI4`,
  `nI4`, `IO$`, `ml$`, `hl$`, `ss$`, `Q8$`, the `registerUriHandler` block, and all 28
  `registerCommand` literals.
- `EXT/webview/index.js` — `lH0`, `dH0`, the `create_worktree` sender, the
  `update_session_state` producer, the terminal live-elsewhere refresh effect.
- `/home/caneff/.vscode-server/bin/645f29cc.../out/server-cli.js` — `openExternal`
  option, `L1`, `mt = process.env.VSCODE_IPC_HOOK_CLI`.
- Probes on this machine, 2026-09-12: `code --version`,
  `code --list-extensions --show-versions`, `code --help`, `ls ~/.claude/projects`,
  `ls ~/.claude/sessions`, status and entrypoint tallies over
  `~/.claude/sessions/*.json`, the live record for this session's own PID, and
  `grep -o '"entrypoint":"[^"]*"'` on this session's transcript.
- https://code.claude.com/docs/en/vs-code — sessions list, command table, URI handler
  and its parameters, tab status dot.
- https://code.claude.com/docs/en/worktrees — `.claude/worktrees/<name>`,
  `worktree-<name>`, `worktree.baseRef` `"fresh"` default.
