# Herdr host: terminal emulator and lightweight editor for WSL2

Research for splitting `herdr` out of VS Code's integrated terminal into a
standalone Windows terminal (running herdr in WSL2) plus a separate
lightweight editor/file-browser window for WSL-resident files. Checked
2026-09-17; version numbers are called out per-claim since this whole area
moves fast.

## Bottom line

**A — terminal: WezTerm.** Stable kitty keyboard protocol support (all four
progressive-enhancement flags), mature WSL launch config (`wsl_domains`,
`unix_domains` for WSL1 native-window mux), SGR 1006 + any-event mouse
reporting, shift+insert bindable via `mouse_bindings`/`keys`; nightly builds
only — the last tagged stable is February 2024 (see "Installed on the
machine"). Runner-up: **Windows Terminal Preview** — its kitty support (PR
microsoft/terminal#19817) shipped in **Preview 1.25** per the March 2026
4sysops writeup; if you want it in the *stable* channel you're waiting on an
unannounced promotion, and Preview installs side-by-side with Stable so this
costs you nothing to try but isn't yet the safe long-term pick. Alacritty is
the fallback if WezTerm's WSL mux setup proves fiddly — same kitty flags,
simpler single-binary config, GPU-accelerated, but no built-in WSL-domain
tab/mux integration (you `wsl.exe` into it like any other launcher target).
Rio is close behind but its Windows keyboard path has an open architectural
limitation (below) that specifically affects agent TUIs like herdr that
push kitty-protocol mode requests in-band.

**B — editor: Zed.** Fully shipped, actively maintained native Windows app
(stable since October 2025) with first-class WSL remoting (a real remote-server
process inside the distro, not just a 9p file share) and a CLI (`zed
path:line:col`, plus `-r`/`--reuse` to replace the workspace in an existing
window) that gives you the `code --reuse-window --goto` equivalent from
inside WSL. Runner-up: VS Code with Remote-WSL and the terminal panel closed
— identical remote-server architecture to Zed (so same file-watching/git
performance), a more mature extension ecosystem, but heavier and is the tool
you're trying to get away from. Third option if you want something truly
minimal: `yazi` in a second terminal pane/tab, with `code`/`zed` wired as its
`edit` opener — zero GUI footprint, but you already have a terminal problem
to solve and this doesn't reduce window count.

## Installed on the machine, 2026-09-17

Corrections to the WezTerm claims below, from doing the install:

- WezTerm **stable is `20240203-110809-5046fc22`** (February 2024) — that is
  what `winget install --id wez.wezterm` gives. "Releases every few weeks"
  is true of the nightly only.
- `winget install --id wez.wezterm.nightly` **fails with "Installer hash does
  not match"**: the manifest pinned `20260915-135123-2658f629` while the
  rolling `WezTerm-nightly-setup.exe` asset had been rebuilt
  (2026-09-17T10:14Z). Installed instead by downloading that asset from
  `github.com/wezterm/wezterm/releases/download/nightly/` and matching its
  SHA-256 to the release's published digest. Result:
  `wezterm 20260917-114457-b09b56c2`, not managed by winget — update by
  re-running the installer.
- Config at `C:\Users\canef\.wezterm.lua`: `default_domain =
  'WSL:Ubuntu-24.04'`, `enable_kitty_keyboard = true` set explicitly, and
  `SHIFT+Insert` bound to `PasteFrom 'Clipboard'` for Wispr Flow.
- **Wispr Flow pastes with Ctrl+V in WezTerm**, not Shift+Insert. A raw-byte
  probe in a herdr pane saw a lone `0x16`: WezTerm's default paste is
  Ctrl+Shift+V, so the key went to the app, which then read the Windows
  clipboard itself from WSL. Binding `CTRL+v` to `PasteFrom 'Clipboard'`
  turned it into one bracketed paste in a single read; Chris reported
  dictation "much faster". Cost: apps in the pane lose a raw Ctrl+V. A bare
  right click is bound to paste too (with `mouse_reporting = true` so it
  applies inside herdr); Ctrl+right-click still reaches herdr. Font is Fira
  Code 12pt and the palette is Dracula Theme Soft, matching VS Code.
- herdr 0.9.0 run in it: Chris checked prefix keys, sidebar clicks and Wispr
  Flow paste — all three worked. The ConPTY kitty-mode caveat below did not
  bite on this WezTerm nightly (it bundles its own `conpty.dll` /
  `OpenConsole.exe`).
- Image paste into Claude Code in WezTerm is **Alt+V**, bound to `SendKey {
  key = 'v', mods = 'CTRL' }`: it forwards the raw Ctrl+V that the paste
  binding swallows. Checked working through herdr.

## Outcome, 2026-09-17: herdr runs in Zed's terminal; WezTerm is the fallback

The two-window plan this note recommends was not where it ended. Later the
same day Chris ran herdr in **Zed's own integrated terminal** (Windows Zed
1.20.2, WSL remote) and ruled "moving to zed only":

- Prefix keys, sidebar clicks, Shift+Enter in a Claude pane, Wispr Flow
  dictation and a plain Ctrl+V image paste all worked with **no custom
  bindings** — where WezTerm needed three. The prediction made beforehand,
  that Zed's terminal lacked the Kitty keyboard protocol and would swallow
  Ctrl+V, was wrong on both counts.
- Zed's WSL terminal is a Linux pty inside the distro (via
  `zed-remote-server`), so ConPTY is not in the path at all.
- **herdr takes one client at a time**: attaching from Zed dropped the
  WezTerm client. The server and panes keep running.
- Zed has no command to pop a terminal into its own OS window (from memory,
  unverified); `workspace: new center terminal` in a second Zed window is
  the untested workaround.
- Zed setup done: `~/.local/bin/zed` symlinks to the Windows install's WSL
  launcher (`…/Programs/Zed/bin/zed` → `zed.exe --wsl user@distro`); a Linux
  Zed 1.13.2 that shadowed it was removed. `zed <path>:<line>` opens into
  the existing window in 0.12 s (first call ~60 s while it downloaded the
  remote server). The ten `uberworkspace.code-workspace` folders open as one
  multi-root window and Zed restores it on launch. Theme is a port of VS
  Code's Dracula Theme Soft; `file_scan_exclusions` hides
  `**/.claude/worktrees`.

### VS Code diagnosis, 2026-09-14 (moved here from `flow/claude/OPERATIONS.md`)

Kept in case herdr ever runs in VS Code's terminal again. Wispr Flow in
herdr needed `{"key": "shift+insert", "command":
"workbench.action.terminal.paste", "when": "terminalFocus"}` in the Windows
user `keybindings.json`. Wispr pasted by simulating Shift+Insert there.
herdr requests Kitty keyboard flags 7 (31 when a pane asks to report all
keys), and with the protocol active VS Code encodes Shift+Insert as a key
(`ESC[2;2~`) instead of pasting, so no text lands and Wispr reports no text
box. The binding runs before the encoder; a raw-byte probe then shows a
bracketed paste. Keep `terminal.integrated.enableKittyKeyboardProtocol` on —
turning it off also fixes Wispr but makes Ctrl+Enter send the same bytes as
Enter. Not the cause: `ui.host_cursor`, editor-vs-panel placement. Same
class: earendil-works/pi#8778. Separately, on 2026-09-17 VS Code's terminal
stopped delivering herdr sidebar clicks for ~36 s until the client was
restarted (server log: no `workspace.focus` events 13:27:58–13:28:34Z while
API requests kept succeeding); cause never found.

## Comparison — A: terminal for herdr (Windows host, WSL2 shell)

| Terminal | Kitty keyboard protocol | Mouse (SGR 1006 / any-event) | WSL launch | Shift+Insert paste | Last release |
|---|---|---|---|---|---|
| **WezTerm** | Yes, all 4 flags, stable for years | Yes, xterm-compatible; bypass via Shift held down | `wsl_domains` (auto from `wsl -l -v`) or `unix_domains` WSL1-only native mux | Not default; bind via `keys`/`mouse_bindings` | Rolling nightly + tagged; changelog active in 2026 |
| **Windows Terminal (Preview)** | Yes, shipped Preview 1.25 (~Mar 2026), full CSI-u rewrite (PR #19817) | Yes, long-standing | `wt -d ~ wsl.exe` or profile with `wsl.exe` commandline | Default binding since PR #4467 (2020) | Preview track updates ~monthly |
| **Windows Terminal (Stable)** | UNVERIFIED — not confirmed merged to Stable channel as of check date | Yes | same as above | Default | Stable quarterly-ish |
| **Alacritty** | Yes, since v0.13.0 (2023-12-27) | Yes, xterm-standard | No native WSL domain; launch `wsl.exe` as `shell` in `alacritty.toml` | Not default; bind via `key_bindings`/paste action | v0.17.0, 2026-04-06 |
| **Rio** | Yes, on by default (`use-kitty-keyboard-protocol = true`) | Yes | `[[shells]]` profiles incl. `wsl.exe`, `Ctrl+Shift+Y` selector | UNVERIFIED default; bindable via `[keyboard]`/`[bindings]` | v0.5.28, 2026-09-06 |
| **Tabby** | **No** — open feature request (Eugeny/tabby#10815), not implemented | UNVERIFIED (VT220-based emulation; SGR mouse presence not confirmed in docs read) | Built-in WSL profile type | UNVERIFIED | Actively released (issue traffic into 2026) |
| **Contour** | Yes, mature, many recent fixes (release notes) | UNVERIFIED explicit SGR mention, but xterm-mode terminal | Spawns shell incl. WSL; known crash-on-spawn-failure bug fixed | UNVERIFIED | Active, recent release-notes entries dated into 2026 |
| **Ghostty** | Yes (spec lists it) on Linux/macOS | Yes on Linux/macOS | **No usable Windows build** — Win32 apprt still mid-upstream (Tier 2/3, `#12167`/tracking issue `mattn/ghostty#1`), earliest maintainer estimate was "late this year" as of an Apr 2026 discussion | N/A on Windows today | N/A on Windows today |
| **kitty** | Reference implementation (not applicable to itself) | Yes, on the platforms it runs on | **No native Windows port.** Runs only via WSLg/X11 or Wayland *inside* WSL2 (kovidgoyal/kitty#640, discussion #7054) — i.e. it would be the WSL-side app, not the Windows-side host, which doesn't fit "standalone Windows terminal" | N/A | N/A (not a Windows host candidate) |
| **Warp** | Yes (spec lists "The Warp terminal") | UNVERIFIED SGR specifics, but modern GPU terminal, presumed yes | Reads WSL distros from registry, surfaces as shell sessions | UNVERIFIED | Weekly Thursday releases (2026 changelog) |
| **Wave** | **No** — open feature request, explicitly named as breaking Vim/Neovim/Helix/Yazi/Kakoune/Nushell/Fish keybindings (wavetermdev/waveterm#2359) | UNVERIFIED | WSL connections via registry + `wsh` helper, similar model to SSH | UNVERIFIED | Active (issue dated Sept 2025, ongoing) |

**Rio/Windows keyboard-protocol caveat**, because it's exactly the herdr
failure mode you're trying to fix: PR raphamorim/rio#1607 documents that
ConPTY consumes the leading `ESC` byte of in-band kitty-protocol mode
requests from a child process, so on Windows Rio now **no-ops** `set/push/pop
keyboard_mode` — an agent TUI that turns on kitty mode itself (rather than
relying on it being already active) will not get real kitty behavior through
Rio on Windows, even though Rio's terminal-level kitty support is on by
default. This is a ConPTY architectural limit, not Rio-specific, and would
equally affect any ConPTY-based terminal an app queries this way — worth
testing directly with herdr rather than trusting the terminal's general
kitty-support claim.

## Comparison — B: lightweight editor/file browser for WSL-resident files

| Candidate | Runs inside WSL / reads via 9p | WSL remoting model | CLI: open file at line, reuse window | Notes |
|---|---|---|---|---|
| **Zed** | Runs a remote-server process inside the WSL distro (own process, not `\\wsl$` file sharing) | `projects: open wsl` / `open folder in wsl`, or `zed` CLI script from inside WSL | `zed myfile.txt:42:10`; `-r`/`--reuse` replaces workspace in an existing window (merged PR zed-industries/zed#38131) | Windows stable since 2025-10-15; full-time Windows team; WSL integration described as built-in, not community add-on |
| **VS Code (Remote-WSL, terminal closed)** | Runs `.vscode-server` inside the distro (`code --remote wsl+<distro>`) — same class of architecture as Zed | Mature, years-old (`code.visualstudio.com/docs/remote/wsl`) | `code --reuse-window --goto <path>:<line>` (existing, exactly what you use today) | This *is* your current tool minus the terminal pane; keeps polling-based file-watcher caveats for very large trees (`remote.WSL.fileWatcher.polling`) |
| **Sublime Text (Windows app, editing via `\\wsl$`)** | Reads via UNC/9p, not a WSL-side process | None (no remote-server model) — forum guidance is explicit: "As a Windows application, Sublime has no direct connection to WSL" | `subl` has `-w/--wait`, `-a/--add`, `-n/--new-window`, no line:col-at-window-reuse in official docs; community script bridges `wslpath` (hans.coffee) | File-watch notifications don't cross the 9p boundary — forum: "file shares don't support that," must manually `Project > Refresh` |
| **Sublime Text (Linux build run inside WSL)** | Native Linux process, real filesystem | N/A — it's local to the distro, needs an X server/WSLg to show | UNVERIFIED CLI-from-Windows-host story | Forum confirms this path fixes file-watch, at the cost of running a GUI app inside WSL |
| **Lite XL** | UNVERIFIED — no primary-source WSL remoting documentation found this session | UNVERIFIED | UNVERIFIED | Not covered in depth — flag for follow-up if it stays a candidate |
| **Lapce** | Windows-native app; SSH remote development (not WSL-domain-native) downloads `lapce-proxy` to the remote host | Remote dev works over SSH only per docs (`docs.lapce.dev/get-started/remote-development`); **WSL "Open folder" is broken** — three open GitHub issues (lapce/lapce#3472, #2979, #3650) since 2022, still open in 2025/2026, workaround is `lapce <path>` from a WSL-side terminal | `lapce <path>` from terminal works per maintainer comment on #3472; no confirmed `path:line` / reuse-window flag found | Actively fixed elsewhere (PR #3841 "Implement folder choosing in remotes" open as of Nov 2025) but the core "click Open Folder while connected to WSL" flow has been broken for 3+ years |
| **Helix / Neovim + tree plugin** | Native Linux process when run inside WSL (terminal-only, no GUI) | N/A — it's not a separate window, it's a pane in the terminal | N/A (not a CLI-from-outside model; you'd `nvim path:line` directly in-session) | Doesn't satisfy "very lightweight IDE/editor... in a second window" — it's terminal-resident, would collapse back into one window |
| **Notepad++** | Windows-native, no WSL awareness | Third-party plugins only (UNVERIFIED which, if any, handle WSL cleanly) | No official line-jump CLI beyond `-n<line>` for local Windows paths | Not WSL-aware out of the box; would need `\\wsl$` path or a wrapper script analogous to the Sublime one |
| **Fleet (JetBrains)** | N/A | N/A | N/A | **Discontinued.** JetBrains stopped distribution 2025-12-22 and will ship no further updates (blog.jetbrains.com/fleet/2025/12/the-future-of-fleet). Not a viable pick. |
| **yazi (terminal file manager)** | Native process inside WSL (you'd run it in a WSL shell pane) | N/A — it's not a GUI, it's your file tree *inside* the terminal | Opener config hands files to any editor, incl. reuse-window flags of that editor | See detail below |
| **broot (terminal file manager)** | Native process inside WSL | N/A | `:e` verb runs `"$EDITOR +{line} {file}"`; documented as adaptable to e.g. `"hx {file}:{line}"` | Docs admit "Broot isn't as fast or feature complete on Windows" — relevant only if you'd ever run it Windows-side, which isn't your case here since files are WSL-resident |

**yazi detail** (`yazi-config/preset/yazi-default.toml`, `sxyazi/yazi` repo):
mouse is opt-in via `[mgr] mouse_events = ["click", "scroll", "drag"]` (also
`"drop"` per the config docs) — click-select and click-preview are covered by
the preset; the maintainer's own tracking issue (sxyazi/yazi#2790, closed by
PR #2925) shows click *behavior itself* (what a left/right/middle click does)
is configurable per-file but not yet a general keymap remap as of that PR.
Opener config is exactly what you'd want to hand a file to Zed/VS Code:

```toml
[opener]
edit = [
  { run = "${EDITOR:-vi} %s", desc = "$EDITOR", for = "unix", block = true },
  { run = "code %s", desc = "VS Code", for = "windows", orphan = true },
]
```
This is a stock example already in yazi's own default config and docs.

## Cross-cutting: `\\wsl$` / 9p performance (applies to Sublime, Notepad++, and
any Windows-native editor reading WSL files without a remote-server model)

Microsoft's own guidance (`learn.microsoft.com/en-us/windows/wsl/filesystems`
and the interop doc) is unambiguous: Linux-process-reads-Linux-files is fast
native ext4; Windows-process-reads-`\\wsl$`-files crosses the 9P protocol and
is explicitly called out as slow, "recommend against... unless you have a
specific reason." A live GitHub issue (microsoft/WSL#4220) measured this
concretely: ~6 MB/s write / ~28 MB/s read over `\\wsl$`, versus ~275 MB/s
write / ~915 MB/s read for a Linux process on its own filesystem — roughly a
30-40x gap. This is why Zed's and VS Code's "run a server process inside the
distro" architecture matters: it keeps file I/O native-Linux-speed and only
pushes UI/diff data back across the boundary, versus Sublime/Notepad++ which
open the file itself across 9p and additionally lose OS-level file-change
notifications (`\\wsl$` doesn't forward inotify events to Windows apps —
confirmed on the Sublime Merge forum thread, corroborated by the general 9p
architecture note in Microsoft's docs).

## Per-candidate notes with citations

### A. Terminals

**WezTerm**
- Kitty protocol: implemented, `enable_kitty_keyboard` config (default true
  since v20220624-141144-bd1b7c5d) —
  https://wezterm.org/config/lua/config/enable_kitty_keyboard.html
- Listed as an implementer in the spec itself —
  https://github.com/kovidgoyal/kitty/blob/f13c8cd4/docs/keyboard-protocol.rst
- Mouse reporting + Shift-bypass documented —
  https://wezterm.org/config/mouse.html
- WSL launch: `wsl_domains` (auto-populated from `wsl -l -v`) —
  https://wezterm.org/config/lua/config/wsl_domains.html ; native-window WSL1
  mux via `unix_domains` — https://wezterm.org/multiplexing.html
- Shift+Insert is not a documented default; bind via `keys`/`mouse_bindings`
  (no dedicated citation found for a shipped default — treat as
  configure-yourself).

**Windows Terminal**
- Kitty protocol merged: PR microsoft/terminal#19817 ("Implement the Kitty
  Keyboard Protocol"), rewrites `TerminalInput`, validated against
  `kitten show-key -m kitty` and several international layouts —
  https://github.com/microsoft/terminal/pull/19817
- Shipped in **Preview 1.25** per third-party release coverage (dated
  2026-03; UNVERIFIED against Microsoft's own release notes page directly,
  only cross-checked via 4sysops) —
  https://4sysops.com/archives/windows-terminal-preview-125-kitty-protocol-settings-search-and-gui-for-key-bindings/
- Original tracking issue with community implementation survey —
  https://github.com/microsoft/terminal/issues/11509
- Shift+Insert default binding added 2020: PR microsoft/terminal#4467 —
  https://github.com/microsoft/terminal/pull/4467 ; confirmed still default
  behavior discussed in microsoft/terminal#8268 and #10625 (2021) and #3324
  (usage nuances, e.g. multiple `keys` entries need separate bindings, not a
  chord array) — https://github.com/microsoft/terminal/issues/3324
- Kitty *graphics* protocol (separate from keyboard) explicitly declined
  pending spec stabilization — cited via ansicode.eversources.app terminal
  reference page, itself citing microsoft/terminal#16264 (secondary source;
  flagged, not a primary Microsoft doc).

**Alacritty**
- Kitty keyboard protocol merged in PR alacritty/alacritty#7125, milestone
  "Version 0.13.0" —
  https://github.com/alacritty/alacritty/pull/7125
- Confirmed release-note entry "Support for kitty's keyboard protocol" and
  ongoing bugfixes through recent changelog entries —
  https://github.com/alacritty/alacritty/blob/master/CHANGELOG.md
- Latest release v0.17.0, 2026-04-06 —
  https://github.com/alacritty/alacritty/releases/tag/v0.17.0 and
  https://alacritty.org/changelog.html
- No WSL-domain concept in Alacritty's config model (it launches an arbitrary
  `shell` program — you'd point that at `wsl.exe`); no dedicated citation
  found for a documented WSL launch snippet, treat as UNVERIFIED /
  "configure yourself."

**Rio**
- Kitty keyboard protocol on by default, `use-kitty-keyboard-protocol = true`
  — https://rioterm.com/docs/features/kitty-keyboard-protocol
- WSL shell profile support via `[[shells]]`, incl. a `Ctrl+Shift+Y` profile
  selector — PR raphamorim/rio#1443 —
  https://github.com/raphamorim/rio/pull/1443
- **Windows ConPTY caveat**: in-band kitty-protocol mode-set requests from a
  child process get their leading ESC eaten by ConPTY; Rio's fix is to
  no-op `set/push/pop_keyboard_mode` on Windows rather than corrupt the
  input stream — PR raphamorim/rio#1607 —
  https://github.com/raphamorim/rio/pull/1607
- Latest release v0.5.28, 2026-09-06 —
  https://rioterm.com/changelog

**Tabby**
- No kitty protocol support: open discussion/feature request, explicitly
  linking it to agent-CLI compatibility (Gemini CLI, Claude Code) —
  https://github.com/Eugeny/tabby/discussions/10815
- Related open graphics-protocol request, also unimplemented —
  https://github.com/Eugeny/tabby/issues/9819
- Separate modifier-key bug (Alt sent as Ctrl) affecting Vim-style bindings
  over SSH from Windows — https://github.com/Eugeny/tabby/issues/10574
- Feature list incl. WSL profile support —
  https://github.com/Eugeny/tabby/blob/master/README.md

**Contour**
- Kitty keyboard protocol: many targeted fixes across releases (F1-F4 codes,
  release-event reporting, modifier encoding, ReportAllKeys gating) —
  https://contour-terminal.org/release-notes/
- Specific bugfix PR for missing release events —
  https://github.com/contour-terminal/contour/pull/1924
- Windows build requirements and known ConPTY mouse-input limitation with
  WSL2 + tmux-like apps, plus external-ConPTY (wezterm's conpty.dll)
  workaround — https://github.com/contour-terminal/contour

**Ghostty**
- No usable stable Windows build; Win32 apprt work is mid-flight, tracked as
  a tiered upstreaming plan (Tier 1 build-fixes landed, Tier 2 apprt skeleton
  "in review", Tier 3 features "TBD") — https://github.com/mattn/ghostty/issues/1
- Maintainer's own timeline guess ("late this year, Nov/Dec") given in a
  Windows-support Q&A discussion, explicitly caveated "don't take that as a
  commitment" — https://github.com/ghostty-org/ghostty/discussions/12290
- Kitty keyboard protocol support exists on Linux/macOS (spec lists it) —
  https://sw.kovidgoyal.net/kitty/keyboard-protocol/

**kitty**
- No native Windows port; only runs inside WSL2 via an X server/WSLg or
  Wayland, i.e. it would be a WSL-side GUI app, not the Windows-side host —
  https://github.com/kovidgoyal/kitty/issues/640 and
  https://github.com/kovidgoyal/kitty/discussions/7054
- Reference implementation of the keyboard protocol —
  https://sw.kovidgoyal.net/kitty/keyboard-protocol/

**Warp**
- Windows availability since Feb 2025 —
  https://www.warp.dev/blog/launching-warp-on-windows
- WSL support: reads distros from Windows registry, surfaces as shell
  sessions — https://warpdotdev-warp.mintlify.app/terminal/overview
- Minimum requirements incl. ConPTY-capable Windows build —
  https://docs.warp.dev/getting-started/quickstart/installation-and-setup/
- Weekly Thursday release cadence, active WSL-specific fixes through 2026 —
  https://docs.warp.dev/changelog/2026/
- Listed as a kitty-protocol implementer in the spec —
  https://sw.kovidgoyal.net/kitty/keyboard-protocol/

**Wave**
- No kitty keyboard protocol; open feature request explicitly names Vim,
  Neovim, Emacs, Helix, Flow, Nushell, Fish, Kakoune, Yazi as tools that
  "break with wave" as a result —
  https://github.com/wavetermdev/waveterm/issues/2359
- WSL connections via registry discovery + `wsh` helper for deeper
  integration — https://github.com/wavetermdev/waveterm/blob/c99022c1/docs/docs/connections.mdx
- Platform support: Windows 10 1809+ (x64) —
  https://www.github.com/wavetermdev/waveterm

### B. Editors / file browsers

**Zed**
- Windows GA announcement, full-time Windows team —
  https://zed.dev/blog/zed-for-windows-is-here
- WSL/SSH remoting architecture: "lightweight remote server process," most
  features (files, git, terminals, tasks, LSPs, debuggers) routed through it
  — same blog post, and https://zed.dev/docs/windows
- CLI reference: `zed myfile.txt:42:10` and `-r`/`--reuse` —
  https://zed.dev/docs/reference/cli.md ; the `--reuse` flag's merged
  implementation — https://github.com/zed-industries/zed/pull/38131

**VS Code (Remote-WSL)**
- `code --remote wsl+<distro> <path>` from a Windows prompt —
  https://code.visualstudio.com/docs/remote/wsl
- File-watcher polling fallback and performance caveat for large trees, same
  page.
- `--reuse-window` (your current flag) documented as working from inside a
  WSL-launched `code`; a known failure mode is a stray native-Windows `code`
  earlier on `$PATH` shadowing the WSL-injected one —
  https://github.com/microsoft/vscode-remote-release/issues/4032

**Sublime Text**
- No native WSL remoting; editing via `\\wsl$` loses file-change
  notifications, requires manual `Project > Refresh` —
  https://forum.sublimetext.com/t/how-to-use-wsl-from-sublime-text/70058
- Community wrapper script for `subl`-from-WSL with `wslpath` translation
  (not first-party) — https://hans.coffee/blog/subl-on-wsl/
- Confirms WSL doesn't forward file-change notifications across to Windows
  apps — https://forum.sublimetext.com/t/current-changes-under-wsl-dont-show-in-sublime-merge/67134

**Lapce**
- Remote development is SSH-only per official docs; explicitly states
  "Currently opening workspaces via Open folder is not possible due to
  recent UI rewrite" for WSL —
  https://docs.lapce.dev/get-started/remote-development
- Three separate open GitHub issues over 2022-2026 confirm this is a
  long-standing, still-open gap: lapce/lapce#3472, #2979, #3650
- A fix PR ("Implement folder choosing in remotes") was open as of
  2025-11-22, not confirmed merged — https://github.com/lapce/lapce/pull/3841

**Fleet**
- Discontinued: no downloads after 2025-12-22, no further updates —
  https://blog.jetbrains.com/fleet/2025/12/the-future-of-fleet/

**Notepad++, Lite XL, Helix/Neovim+tree**
- No primary-source WSL-remoting documentation surfaced this session for
  Notepad++ or Lite XL specifically — flagged UNVERIFIED below rather than
  guessed. Helix/Neovim-in-terminal is architecturally a terminal-resident
  editor, not a separate window, so it doesn't answer the "second, very
  lightweight IDE window" half of the ask even though it runs natively fast
  inside WSL.

**yazi**
- Mouse config (`[mgr] mouse_events`) and opener/rule system —
  https://github.com/sxyazi/yazi/blob/main/yazi-config/preset/yazi-default.toml
- Per-click-behavior configurability tracked/partially closed via
  https://github.com/sxyazi/yazi/issues/2790 and merged PR #2925

**broot**
- `:e` edit verb, `"$EDITOR +{line} {file}"`, documented as adaptable to
  other editors' line-flag syntax — https://dystroy.org/broot/common-problems/
- Windows caveat ("isn't as fast or feature complete on Windows") on the same
  page — not directly relevant since your files are WSL-side, but relevant
  if broot itself were ever run Windows-side.

**WSL filesystem performance (cross-cutting)**
- Official recommendation to keep Linux-tooled projects on the Linux
  filesystem, and Windows-tooled projects on NTFS —
  https://learn.microsoft.com/en-us/windows/wsl/filesystems
- Interop doc's explicit performance table (fast/slow per direction) —
  https://learn.microsoft.com/en-us/windows/dev-environment/wsl-interop
- Concrete throughput numbers for `\\wsl$` vs native —
  https://github.com/microsoft/WSL/issues/4220

## Unverified / test on the machine first

- **Windows Terminal Stable channel**: whether kitty keyboard protocol has
  been promoted out of Preview 1.25 into Stable as of today. Check
  `wt --version` and the Stable release notes directly on the machine.
- **Tabby mouse reporting** (SGR 1006 / any-event): not confirmed from its
  README or issue tracker in this pass — its VT220-based emulator's exact
  mouse-mode support wasn't directly documented in what I read.
- **Contour, Rio, Warp shift+insert default behavior**: none of their docs
  explicitly state a shipped Shift+Insert-paste default; assume
  configure-yourself until checked in the app's own keybinding settings.
- **Contour explicit SGR 1006 support**: release notes show extensive kitty
  keyboard work but no explicit mouse-protocol-mode citation was found;
  Contour is xterm-mode-capable in general, so this is likely yes but
  unconfirmed against a primary doc page.
- **Warp SGR mouse specifics**: platform docs describe WSL/shell integration
  but not mouse-protocol details directly.
- **Lite XL and Notepad++ WSL remoting**: no primary source found this
  session — needs its own targeted look if either stays a candidate.
- **Sublime Text Linux build run inside WSL, opened from the Windows host**:
  the forum thread confirms running Sublime natively inside WSL fixes file
  watching, but doesn't describe a CLI bridge from the Windows-side shell
  into that WSL-resident GUI instance — would need X server/WSLg setup
  testing.
- **yazi keymap-level mouse remapping** (not just per-file click behavior):
  PR #2925 closed the per-file-click-behavior issue; whether general
  left/right/middle-click actions are remappable via `keymap.toml` as of the
  currently released version wasn't confirmed — check current yazi docs
  directly.
- **Ghostty Windows timeline**: maintainer's "late 2026" estimate was
  explicitly caveated as non-committal in the linked discussion; don't plan
  around it.
