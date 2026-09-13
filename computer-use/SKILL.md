---
name: computer-use
description: Drive or inspect a visible Windows window from WSL — read a window's title or content, click, type, or screenshot it. Use when Chris says "look at that window", "click X in <app>", "what does <window> say", or otherwise names a specific visible window or app to inspect or control.
---

# computer-use

Chris's desktop is Windows; WSL is the shell only. This skill reaches the real
Windows desktop from here — three backends, in order of preference. Never
fires on your own intent: load it only when Chris names a window, app, or
on-screen thing for you to look at or drive. When Chris is the one who needs
to look at something himself, that's `wslview` /
`code --reuse-window --goto`, not this skill
(`~/.agents/skills/flow/claude/VISUAL-INSPECTION.md`); a rendered HTML page
you produced goes through `shot-scraper`, not this skill either (see below).

Never `xdotool`, WSLg, or any Linux-GUI approach: it acts on a display Chris
can't see. Never `wsl --shutdown`.

## Backends

**1. Windows-MCP — primary.** MCP server (CursorTouch, MIT, pinned `0.8.5`)
reached over the `powershell.exe` bridge. Covers both native windows and, via
`use_dom=True`, the DOM of a real Chrome/Edge/Firefox window — the one thing
PowerShell UI Automation can't do. Tools: `Snapshot`/`Screenshot` for state,
`Click`/`Type`/`Scroll`/`Move`/`Shortcut`/`WaitFor` for input, `App` for
launching and resizing. Registered with (get `<user>` from WSL with
`powershell.exe -NoProfile -Command '$env:USERNAME'`):

```
claude mcp add windows-mcp --transport stdio -s user -- powershell.exe -Command "C:/Users/<user>/.local/bin/uvx.exe windows-mcp@0.8.5 serve"
```

It also ships `PowerShell`, `Registry`, `Process` and `FileSystem` tools — a
wide grant. Treat those four as arbitrary-code-execution-on-Windows; don't
reach for them casually. First run installs Windows-side dependencies and can
time out — that's not a broken server, restart it.

**2. PowerShell UI Automation — the zero-install floor.** In-box on Windows
PowerShell 5.1, no `uv`, no MCP, nothing to register. Reaches window
enumeration, control-pattern inspection, `SendKeys` input, and
`System.Drawing` capture — window-level only, no browser DOM. Use this when
Windows-MCP isn't registered yet, or for anything that's just "is the window
there / bring it forward / read its title / screenshot it." `inspect-windows.ps1`
in this skill's own directory enumerates every top-level window's
`Name`/`ClassName`; run it (or any other `.ps1`) with an absolute path so the
command isn't cwd-dependent:

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w ~/.agents/skills/computer-use/inspect-windows.ps1)"
```

A one-liner works too, but heredoc quoting crosses the WSL/Windows boundary
badly — write the script to a file and pass `-File` rather than fighting
`-Command` quoting.

**3. Terminator (mediar-ai) — second choice for the browser half.** Rust
UI-automation engine with an MCP server and a Chrome extension that drives
the real, already-logged-in browser session — no relogin, keeps cookies and
auth, and sidesteps both Chrome 136+'s default-profile block and the NAT
loopback problem that rules out CDP. Reach for it only if Windows-MCP's
`use_dom=True` doesn't read a page well enough. No documented WSL bridge (its
README never mentions WSL); the Windows-side npm package trails its own repo
by two tags. Register with the Windows-side npm binary through the same
`powershell.exe` bridge pattern as Windows-MCP:

```
claude mcp add terminator --transport stdio -s user -- powershell.exe -Command "npx.cmd -y terminator-mcp-agent@0.24.28"
```

Pinned to the npm version the line actually fetches (`0.24.28`, itself two
tags behind the repo's `v0.24.32`) rather than `@latest` — the skew is the
whole reason this is second choice, and `@latest` would silently outrun the
number this file cites.

## What doesn't apply here

- **Claude Code's built-in `computer-use` MCP server** — macOS only, absent
  from `claude mcp list` on this machine.
- **Claude in Chrome** — states WSL is unsupported.
- **Playwright/CDP** — browser-only, and the Windows loopback port is
  unreachable under this machine's `nat` WSL networking mode; would need
  Windows-side `node.exe` even if it worked.
- **shot-scraper** — covers rendering an HTML page you produced, headless.
  Can't read the real logged-in visible Chrome window or a native window;
  that gap is what this skill fills.

## The destination: Windows' own first-party MCP servers

Build `26200.9445` already stages first-party `WindowUnderstanding` and
`Windowing` MCP manifests (MIT, Microsoft) declaring `get_window_list`,
`get_window_ui_context`, `invoke_control`, `invoke_action`, `snap_window`,
`close_window` — real window inspection and input, no third party. Not
reachable yet: `odr.exe` is absent, the `WindowsAI` registry key is empty,
and Microsoft's MCP-host quickstart wants build `26220.7262+`. No first-party
server covers a browser DOM. Re-check this once the build catches up, and
drop Windows-MCP and Terminator in its favor if it clears the same bar.

## Verifying it's working

A live inspection from WSL, minimal and cheap — no install needed for this
one, same command as backend 2 above:

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w ~/.agents/skills/computer-use/inspect-windows.ps1)"
```

A non-empty list of real window titles is the check.
