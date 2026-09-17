# Visual inspection (read when showing me a file, or looking at a rendered page, window, or image)

Pointer target for `CLAUDE.md` § Gotchas.

## Showing me a file

Open it for me; never print a path and ask me to open it. Why: that hands me
a step your own hands can do.

- A source file: `zed <path>[:line[:col]]` — it lands in the Zed window I
  already have open (the ten repos of `~/src/uberworkspace.code-workspace`;
  Zed restores it on launch). `zed` on the WSL PATH is a symlink to the
  Windows install's own launcher
  (`/mnt/c/Users/canef/AppData/Local/Programs/Zed/bin/zed`), which runs
  `zed.exe --wsl caneff@Ubuntu-24.04`; never install a Linux Zed over it. A
  path under `.claude/worktrees` still opens, but Zed's
  `file_scan_exclusions` hides those directories from its tree and search.
  Switched from `code --reuse-window --goto` on 2026-09-17.
- A rendered HTML page I should look at myself: `wslview <file>` opens it in
  my Windows browser. That is my opener, not your reader — you read the page
  through `shot-scraper` below.

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
  element, which is usually the crop you actually wanted.
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
