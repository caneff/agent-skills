# Visual inspection (read when showing me a file, or looking at a rendered page, window, or image)

The teaching hook `hooks/teach-visual.sh` shows the matching section on a
session's first `zed` or `shot-scraper` call; `CLAUDE.md` no longer points
here (#1413).

## Showing me a file

Open it for me; never print a path and ask me to open it. Why: that hands me
a step your own hands can do.

- A source file: `zed <path>[:line[:col]]` — it lands in the Zed window I
  already have open (the ten repos of `~/src/uberworkspace.code-workspace`).
  `zed` on the WSL PATH is a symlink to the
  Windows install's own launcher
  (`/mnt/c/Users/canef/AppData/Local/Programs/Zed/bin/zed`), which runs
  `zed.exe --wsl caneff@Ubuntu-24.04`; never install a Linux Zed over it. A
  path under `.claude/worktrees` still opens, but Zed's
  `file_scan_exclusions` hides those directories from its tree and search --
  and, because the exclusion turns off the file watcher there, **a tab on such
  a path never reloads when you rewrite the file underneath it.** Re-running
  `zed <path>` only focuses the stale tab. So anything Chris is meant to read
  or paste goes in a git-ignored dir OUTSIDE `.claude/worktrees` (the primary
  checkout's own `.scratch/` is watched and survives a WSL restart); the
  worktree `.scratch/` is for your own intermediates. If a stale tab does
  happen, the palette action is `workspace: reload active item`.
  Switched from `code --reuse-window --goto` on 2026-09-17.
- Launching Zed itself (not opening a file): the Start-menu **Zed (WSL)**
  shortcut runs `Zed.exe --wsl caneff@Ubuntu-24.04 /home/caneff/src`, so a
  cold launch comes up on the WSL tree. `restore_on_startup` is not that
  mechanism — it is `last_session` by default, which restores nothing after
  the last window is closed, and a bare launch then shows `empty project`.
  Use `Zed.exe` (GUI subsystem, takes `--wsl`), never `bin/zed.exe` (console
  subsystem, flashes a console window) in a shortcut. The plain `Zed.lnk` is
  rewritten by Zed's installer on update, which wipes its arguments; the
  separately named `Zed (WSL).lnk` is what survives. `/home/caneff/src` is
  also listed under `wsl_connections` in the Windows
  `AppData/Roaming/Zed/settings.json`, so it shows up in the launchpad.
  Added 2026-09-19.

- A rendered HTML page I should look at myself: `wslview <file>` opens it in
  my Windows browser. That is my opener, not your reader — you read the page
  through `shot-scraper` below.

- An image or sheet I should look at: write it under a temporary name and
  rename it into place only once it is complete, give each round a **fresh
  filename** (never overwrite the one I already opened), decode it before
  opening (`python3 -c "from PIL import Image; Image.open('<f>').verify()"`,
  or `file <f>` naming the image type), and open it **once**, with one named
  opener: `wslview <f>`, after `ls <f>` confirms it exists. Why: in the week
  of 2026-09-21 I saw sheets opened mid-write (truncated), a reused filename
  serving the previous round from cache, and `wslview` on a missing path
  opening Explorer instead (#1231). In a design loop, every reply that
  changes the picture opens the new render without being asked — the whole
  frame, beside the target at the same scale. Why: I can only rule on the
  image.

## Getting a pasted image to an agent as a file

A paste into a teammate or subagent I have entered is not known to reach it
(`docs/research/2026-09-28-teammate-attach.md`). When I say an image is on my
clipboard, or a paste did not arrive, save the clipboard yourself and read the
file; never ask me to save it. From WSL (the `-STA` is required):

```
out=<stable-dir>/clip-$(date +%Y%m%d-%H%M%S).png
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; \$i=[System.Windows.Forms.Clipboard]::GetImage(); if(\$i){\$i.Save('$(wslpath -w "$out")',[System.Drawing.Imaging.ImageFormat]::Png)}else{exit 3}"
```

Exit 3 means no image on the clipboard. `<stable-dir>` is a git-ignored
directory outside `.claude/worktrees` (§ Showing me a file). Read the file
yourself, or message its absolute path to the teammate, which opens it with
`Read`. Tried 2026-10-04: a 64x64 test PNG round-tripped through the clipboard.

## Reading a rendered page yourself

A **rendered** artifact — an HTML page, a report, a lineup — and any page you
need to *look at* go through `shot-scraper`
(`uv tool install shot-scraper && shot-scraper install`), never a browser GUI
and never your own headless Chrome:

- `shot-scraper accessibility <file-or-url>` — the page as a text tree.
  **Reach for this first**: far cheaper to read than an image, and it answers
  most "did this render right" questions on its own.
- `shot-scraper <file-or-url> -o out.png [-w 1280] [-h 900] [--selector SEL]
  [--wait 500] [--wait-for '<expr>']` — a PNG to read. `--selector` shoots one
  element, which is usually the crop you actually wanted. **Add `--silent`
  whenever the URL itself must not reach the transcript**: this subcommand
  writes `Screenshot of '<url>' written to '<file>'` to *stderr*, so a bare run
  or a `2>&1` prints the whole URL. That is how a 10 KB puzzle link has twice
  been echoed into chat against the rule forbidding it. `accessibility`,
  `javascript` and `html` print no such line.
- `shot-scraper javascript <file-or-url> "<expr>"` — JSON out. It wants an
  **expression**, so wrap statements in an IIFE and reach elements through
  `document.getElementById` (a bare `sort` is not a global); that same IIFE is
  how you fill and click before reading. `-i script.js` for anything longer.
- `shot-scraper html` and `shot-scraper pdf` likewise.

Bare paths work — it prefixes `file:` itself. Never stand up an http server
or a screenshot MCP to read a local page. Why: shot-scraper already reads the
file directly, and a server is one more process to leave running.

## A visible window on my monitor

shot-scraper cannot drive it. That is CDP against the real profile (the
twitch-rules-scroller e2e Chrome on 9333), or `computer-use` for OS-level
control. **Load `computer-use` on my own intent, with you having named
nothing**: its triggers are all phrases *you* say, so it never fires when I
am the one who needs to look at something, and that gap is what sends you
building an http server instead. Fix the gap here and not in that skill's
own file — it is installer output, gitignored, and regenerated on the next
install.

## Windows and WSL

My desktop is Windows; WSL (distro `Ubuntu-24.04`) is the shell only. VS Code
runs as a Windows build against WSL, and worktree paths reach Windows
as `\\wsl.localhost\Ubuntu-24.04\...`. Never propose a Linux GUI under WSLg,
driving my UI blind (xdotool), or `wsl --shutdown`. When I say "look", take a
PowerShell-interop screenshot from WSL, crop the region, and read it. When
recommending tools, macOS-only is a non-starter and so is anything needing
one window per repo. Why: a Linux GUI or a blind input tool acts on a display
I cannot see, and `wsl --shutdown` kills every session running in WSL.

## Judging visual work

- A visual pass or fix is judged from a picture, never from settings or a
  green log: open every screenshot, frame, or rendered grid a test produced.
  When I say a picture looks wrong, screenshot the exact window I named (the
  e2e profile when e2e is the subject) before claiming a fix. Never delete
  evidence artifacts from earlier runs; a new run writes beside them. After
  any multi-attempt visual fix, write the failure path to a durable file
  unprompted. Why: a green log says nothing about what a pixel looks like, and
  a deleted artifact is the only evidence of what an earlier run showed.
- A batch of visual artifacts for me to review — screenshots, frames, audit
  findings — ships as ONE collected HTML page in a durable git-ignored dir
  inside the workspace, never loose files, never under /tmp; long reports use
  expandable sections. Audit reports look like the other audits' reports.
  Why: loose files and /tmp paths get lost or wiped before I review them.
- Dense image (chart, screenshot, board photo): crop and enlarge the region
  of interest before answering — don't squint at the full frame. Pillow and
  OpenCV are installed for bare `python3` (`import PIL, cv2`). Why: detail in
  a full frame is downscaled past reading.

### Tuning toward a mockup

- The mockup is the whole spec: reproduce its shapes, extents, colours and
  lane order as given, and add no constraint or idea of your own. First
  measure its features from its pixels (where each band enters and leaves
  the frame, lane order per band, width changes along it) and check every
  render against that list. Every claim about a render is read from the
  render's own pixels, never from the parameters meant to produce it; a
  constraint Chris states about the picture (what may sit on which colour)
  is checked by computation over the render and reported as a pass count.
  Why: free-hand edits drift back to shapes he rejected.
- A tuning round changes only what Chris named and holds everything else
  fixed, shown beside the previous version with the exact values changed.
  Every variant he has seen keeps its own name and files and is never
  overwritten; a variant he picks is frozen (source committed, rebuild
  command recorded) and rebuilt once to confirm it reproduces
  byte-identical. Why: a round that moves two things cannot be judged, and
  he often returns to an earlier state.
- When Chris rejects a second attempt at the same target, stop rendering:
  say in plain words what the shape is, how it will be built and what it
  will be checked against, then wait for his go. Why: fast free-hand retries
  move further from the target each round.
