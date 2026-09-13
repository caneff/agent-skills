# OS-level computer-use tools from WSL2 after Orca

Research ticket [#702](https://github.com/caneff/agent-skills/issues/702), wayfinder map
[#700](https://github.com/caneff/agent-skills/issues/700). Scored the
[#488](https://github.com/caneff/agent-skills/issues/488) way: pinned version, read from
source or official docs, hard rejects listed explicitly.

**Question.** `computer-use` today wraps `orca computer` for native Windows windows,
external browser windows, and app webviews. Orca is being removed. What OS-level
computer-use tool, reachable from WSL2, replaces it — or does the skill retire?

**Answer.** The skill does **not** retire. Adopt **Windows-MCP 0.8.5** over its documented
`powershell.exe` bridge, with **in-box PowerShell UI Automation** as the zero-install floor
underneath it. Claude Code's own `computer-use` server is macOS-only and is a hard reject
on this machine.

**Revision, 2026-09-12 (second pass).** Ticket reopened to score three missed candidates:
Terminator, Microsoft's native MCP support in Windows 11, and the vision-driven agents
(OmniParser, UI-TARS). The primary pick is unchanged, but two things were added: Terminator
is now the named second choice for the browser half, and **Windows' own first-party
`WindowUnderstanding` and `Windowing` MCP servers are the destination** — their manifests are
already on disk on this machine, but the registry that serves them is not yet enabled in this
build. The browser-half reasoning was also corrected: `page-shot`/`page-eval` are absent **by
design**, not missing.

## Environment, as measured on 2026-09-12

Every line below was run from this WSL2 shell, not inferred.

| Fact | Command | Result |
| --- | --- | --- |
| Claude Code CLI | `claude --version` | `2.1.269 (Claude Code)` |
| Windows PowerShell | `powershell.exe -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'` | `5.1.26100.9444` |
| WSL networking mode | `wslinfo --networking-mode` | `nat` |
| WSL interop | `cat /proc/sys/fs/binfmt_misc/WSLInterop` | `enabled` |
| Windows node | `node.exe --version` | `v24.15.0` |
| Windows Python | `python.exe -c 'import sys;print(sys.version)'` | `3.14.4 … MSC v.1944 64 bit` |
| Windows uvx | `where.exe uvx.exe` | `C:\Users\canef\.local\bin\uvx.exe` |
| AutoHotkey | `ls "/mnt/c/Program Files/AutoHotkey"` | absent |
| `pywinauto`, `uiautomation`, `comtypes`, `win32gui`, `playwright` on Windows Python | `python.exe -c "import importlib.util …"` | all `False` |
| Built-in `computer-use` MCP server | `claude mcp list` | absent; only `google-docs`, `exa`, `c4ai` |
| `shot-scraper` | `shot-scraper --version` | `1.11` (the sanctioned renderer, per merged PR #693) |
| `page-shot` / `page-eval` | `gh pr view 693` | **absent by design** — #691 was rescoped and the scripts deleted in favour of `shot-scraper` |
| Windows build | `[System.Environment]::OSVersion.Version` + registry | `10.0.26200`, UBR `9445`, DisplayVersion `25H2` |
| Windows `odr.exe` | `where.exe odr.exe` | absent |
| Windows `npx.cmd` | `where.exe npx.cmd` | `C:\Program Files\nodejs\npx.cmd` |

Two measurements decide most of the scoring below.

**UI Automation reaches the real Windows desktop from WSL, today, with nothing installed.**
Loading `UIAutomationClient` and `UIAutomationTypes` in `powershell.exe` from this shell and
walking `AutomationElement::RootElement` returned three live top-level windows:

```
count=3
ScojoSolves - Twitch - Google Chrome | Chrome_WidgetWin_1
#698 Retire... - uberworkspace (Workspace) [WSL: Ubuntu-24.04] - Visual Studio Code | Chrome_WidgetWin_1
Steam | SDL_app
```

A follow-up call on the `Steam` element reported
`patterns=WindowPatternIdentifiers.Pattern,TransformPatternIdentifiers.Pattern`, and
`Add-Type -AssemblyName System.Windows.Forms,System.Drawing` plus
`[System.Windows.Forms.SendKeys]` both resolved. So inspection, window move/resize, keyboard
input, and screen capture are all in-box on the Windows side and all reachable over interop.

**Bidirectional stdio survives the WSL/Windows boundary.** This is what lets a Windows-side
MCP server be spawned by a WSL-side Claude Code:

```
$ echo '{"jsonrpc":"2.0","id":1,"method":"ping"}' | powershell.exe -NoProfile \
    -Command '$l=[Console]::In.ReadLine(); [Console]::Out.WriteLine("ECHO:"+$l)'
ECHO:{"jsonrpc":"2.0","id":1,"method":"ping"}
```

**The loopback direction does not work.** Networking mode is `nat`, so WSL's `127.0.0.1` is
not Windows' `127.0.0.1`. This matches the existing finding in
`~/src/twitch-rules-scroller/docs/research/cdp-real-chrome.md`: "NAT mode has no supported
path to a loopback-bound Windows service … mirrored mode lets WSL2 dial `127.0.0.1:<port>`
directly." That repo's own `AGENTS.md` states it as a rule: "it binds Windows' loopback,
which WSL cannot reach (WSL's 127.0.0.1 is a different loopback, and the gateway IP hangs)."
The working crossing pattern in that repo is not a socket at all — `e2e.sh` runs Windows
`node.exe` on the harness over a `\\wsl.localhost` UNC path produced by `wslpath -w`,
carrying environment across with `WSLENV`.

## Scoring table

Reach, browser, native, and harness are scored ✅ full / ⚠️ partial / ❌ none.

| Candidate | Pinned version | WSL2→Windows reach | External browser | Native window inspect + input | Runs under Claude Code | Alive | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Windows-MCP** (CursorTouch) | `0.8.5` (PyPI; tag `v0.8.5`, 2026-08-01; head `787385ec5f96`, 2026-09-12) | ✅ documented `powershell.exe` bridge | ✅ `use_dom=True`, Chrome/Edge/Firefox | ✅ UIA tree + click/type/scroll/shortcut | ✅ stdio MCP server | ✅ MIT, 6,984 stars, pushed 2026-09-12 | **Adopt** |
| **PowerShell UI Automation** (in-box) | Windows PowerShell `5.1.26100.9444` | ✅ verified live | ❌ no DOM; window-level only | ✅ verified live | ✅ plain Bash calls | ✅ ships with Windows | **Adopt as floor** |
| **Terminator** (mediar-ai) | npm `terminator-mcp-agent` `0.24.28` (2026-01-28) vs tag `v0.24.32` (2026-04-05); head `73a381c0c1c3`, 2026-06-02 | ⚠️ Windows-only binary; no documented WSL path | ✅ real browser session via Chrome extension | ✅ UIA tree + click/type/capture | ✅ `claude mcp add` one-liner | ⚠️ MIT, 1,637 stars, no commit since 2026-06-02; vendor pivoted to a paid IDE | **Second choice** |
| **Windows first-party `WindowUnderstanding` + `Windowing` MCP servers** | manifests `0.1.0`, MCP protocol `2025-11-25`, on disk at build `26200.9445` | ⚠️ Windows-side; ODR not enabled in this build | ❌ no DOM tools | ✅ `get_window_list`, `get_window_ui_context`, `invoke_control`, `invoke_action`, `snap_window` | ⚠️ ODR expects an MSIX host with package identity | ✅ Microsoft, public preview | **Revisit at build 26220.7262+** |
| Microsoft OmniParser v2 | `v.2.0.1` (2025-09-12); head `354021201345`, 2026-07-20 | ❌ | ❌ | ❌ perception only, no input | ❌ | ✅ | **Hard reject: not a driver** |
| ByteDance UI-TARS / Agent TARS | `UI-TARS-desktop` `v0.3.0` (2025-11-04), head pushed 2026-09-11; `UI-TARS` model repo pushed 2026-01-27 | ❌ | ✅ own browser operator | ✅ own computer operator | ❌ own agent, own CLI/desktop app | ✅ | **Hard reject: brings its own agent** |
| Playwright `connectOverCDP` | `1.63.0` (npm, 2026-09-04) | ⚠️ needs Windows `node.exe`; CDP port unreachable under NAT | ⚠️ own profile only; Chrome 136+ ignores the flag on the default profile | ❌ no native windows | ✅ plain Bash calls | ✅ | Browser-only, already covered |
| pywinauto | `0.6.9` (PyPI; release 2025-01-06; pushed 2026-05-23) | ⚠️ interop, but needs install | ❌ | ✅ UIA/Win32 backends | ⚠️ needs a hand-written CLI wrapper | ⚠️ no release in 20 months | Reject: cost, no wrapper |
| win32-mcp-server | `2.5.1` PyPI vs tag `v2.6.1` (2026-06-11); head 2026-08-23 | ⚠️ interop, needs install | ⚠️ OCR/coordinates only | ✅ 6 UIA tools + OCR | ✅ stdio MCP | ⚠️ 4 stars, one maintainer, PyPI behind the tag | Reject: bus factor, release skew |
| Claude Code built-in `computer-use` | `2.1.269` | ❌ | ❌ | ❌ | ✅ | ✅ | **Hard reject: macOS only** |
| Claude in Chrome | extension ≥ `1.0.36` | ❌ | ❌ | ❌ | ✅ | ✅ | **Hard reject: unsupported in WSL** |
| Claude Desktop computer use (Windows) | Desktop research preview | n/a | ✅ | ✅ | ❌ separate agent | ✅ | **Hard reject: brings its own agent** |
| Anthropic computer-use reference impl | `claude-quickstarts`, commit `5264b72`, 2026-08-21 | ❌ Linux X11 in Docker | ⚠️ container's own browser | ⚠️ container's own desktop | ❌ own agent loop + Streamlit | ✅ | **Hard reject: wrong desktop, own agent** |
| Windows 365 for Agents MCP | `mcp_W365ComputerUse` (Microsoft Learn, 2026-08-04) | ❌ cloud PC, not this desktop | ✅ (Edge, in the cloud PC) | ✅ (in the cloud PC) | ✅ MCP | ✅ | **Hard reject: not the local desktop** |
| nut.js | `@nut-tree/nut-js`, repo pushed 2024-05-01 | ⚠️ needs Windows node | ❌ | ✅ | ⚠️ library, needs a wrapper | ❌ repo frozen; no OSS license; commercial | **Hard reject: sunsetting as OSS** |
| AutoHotkey | not installed | ⚠️ interop after install | ❌ | ⚠️ input only, no structured tree | ⚠️ script-per-action | ✅ | Reject: no inspection |

## Candidate notes

**Windows-MCP (CursorTouch) — adopt.** The only candidate that clears every column. Its
README documents the exact bridge this machine needs, under a heading "WSL (Windows
Subsystem for Linux)": *"If you run Claude Code from WSL, the MCP server must still execute
on the Windows side (it needs Windows APIs for UI automation). Use `powershell.exe` as the
command to bridge WSL and Windows"*, with the registration line
`claude mcp add windows-mcp --transport stdio -s user -- powershell.exe -Command "C:\Users\<user>\.local\bin\uvx.exe windows-mcp serve"`.
That path is not hypothetical here: `where.exe uvx.exe` returns
`C:\Users\canef\.local\bin\uvx.exe`, exactly the documented location, and the stdio echo
test above shows the transport survives the boundary. The tool surface covers both halves of
what `orca computer` did — `Snapshot` and `Screenshot` for state, `Click`, `Type`, `Scroll`,
`Move`, `Shortcut`, `WaitFor` for input, `App` for launching and resizing windows, and a
`use_dom=True` mode described as focusing *"exclusively on web page content, filtering out
browser UI elements … Supports Chrome, Edge, and Firefox (Firefox uses an IAccessible2
fallback since it doesn't expose `RootWebArea` via UIA)"*. MIT licensed, 6,984 stars, head
commit `787385ec5f96` dated 2026-09-12 — the most actively maintained thing in this survey.
Prerequisites it states: Python 3.13+ and `uv` on the **Windows** side, and English as the
Windows display language or else disable `App-Tool`.

Two costs worth naming before adoption. It ships a `PowerShell` tool, a `FileSystem` tool,
a `Registry` tool and a `Process` tool, so enabling it hands the session arbitrary Windows
code execution and registry writes — wider than `orca computer` ever was, and worth
narrowing at the permission layer. And its README warns that first run *"may take a minute
or two because of installing the dependencies … In the first run the server may timeout
ignore it and restart it"*, which will look like a broken server the first time.
[Repo](https://github.com/CursorTouch/Windows-MCP) ·
[PyPI](https://pypi.org/project/windows-mcp/)

**PowerShell UI Automation — adopt as the floor.** Not a product, a capability that is
already present and already verified working from this shell. It needs no install, no
marketplace, no `uv`, and no new trust boundary beyond the `powershell.exe` interop the
dev's other repos already depend on. It enumerates top-level windows, reports the automation
patterns each one supports, and reaches `SendKeys` and `System.Drawing` for input and
capture. What it does not give you is a browser DOM: a Chrome window comes back as
`Chrome_WidgetWin_1` with a title, and getting inside the page means walking the raw UIA
tree by hand. That makes it the right floor and the wrong ceiling — good for "is the window
there, what is it called, bring it forward, screenshot it", not for "click the third row of
that table".

**Terminator (mediar-ai) — second choice, and the best answer for the browser half.** Read
at head `73a381c0c1c3` (2026-06-02). A Rust UI-automation engine for Windows that ships an
MCP server, and it advertises the Claude Code path in its own README as a one-liner:
`claude mcp add terminator "npx -y terminator-mcp-agent@latest"`. Its three stated
advantages are exactly the gap `orca computer` left behind: *"Uses your browser session — no
need to relogin, keeps all your cookies and auth"*, *"Doesn't take over your cursor or
keyboard — runs in the background without interrupting your work"*, and *"Works across all
dimensions — pixels, DOM, and Accessibility tree for maximum reliability"*. Browser control
comes through a Chrome extension rather than CDP, which sidesteps both the Chrome 136+
default-profile restriction and the NAT loopback problem. MIT, 1,637 stars, SDKs in Rust,
TypeScript and Python.

Three things put it behind Windows-MCP rather than ahead of it. **It is Windows-only and
says so twice**, with a support matrix marking macOS and Linux "No" on every row and the
note *"Terminator currently supports Windows only. macOS and Linux support is not
available."* The engine being Windows-native is fine — Windows-MCP is too — but Terminator
documents **no WSL path at all**: `grep -i wsl` over its README returns nothing, so the
`powershell.exe` bridge would be the dev's invention rather than a supported configuration.
The one-liner as written would run `npx` under WSL Linux Node and fail on a Rust Windows
binary; it would have to become `powershell.exe -Command "npx.cmd -y terminator-mcp-agent"`,
and `npx.cmd` does exist on the Windows side at `C:\Program Files\nodejs\npx.cmd`.
**Liveness is the real problem.** The npm package `terminator-mcp-agent` is pinned at
`0.24.28`, published **2026-01-28** — seven and a half months old — while the newest GitHub
release is `v0.24.32` from 2026-04-05 and the last commit to `main` is 2026-06-02. The npm
artifact the install line actually fetches is two tags behind the repo, the same skew that
rejected `win32-mcp-server`. And the README's own newest news item is *"01/09/26 - Mediar IDE
(Cursor for Windows automation) is in public access"*, a paid product; the OSS core has not
moved since. Against Windows-MCP, whose head commit is dated today and whose WSL bridge is
documented, that is second place. Keep it named in the skill as the fallback if Windows-MCP's
`use_dom=True` turns out not to read the dev's Chrome well enough.
[Repo](https://github.com/mediar-ai/terminator) ·
[npm](https://www.npmjs.com/package/terminator-mcp-agent)

**Windows' own first-party MCP servers — the destination, not yet the answer.** This is the
strongest finding of the second pass, and it was read off this machine's own disk rather than
from a blog. Microsoft's MCP-on-Windows stack is the **On-device Agent Registry (ODR)**, and
the shell servers it serves ship as manifests in
`C:\Windows\SystemApps\MicrosoftWindows.Client.Core_cw5n1h2txyewy\ShellMcpServers\Assets`.
Ten are present on build `26200.9445`: `AppInfo`, `AppLaunch`, `File`, `FileSearch`,
`Magnifier`, `Settings`, `SystemInfo`, `Troubleshooting`, **`WindowUnderstanding`** and
**`Windowing`**. The last two are not app actions — they are precisely window inspection and
input. Parsed from `WindowUnderstandingMcpManifest.json` (`display_name` "Window
Understanding MCP Server", version `0.1.0`, `license` MIT, author Microsoft Corporation,
protocol `2025-11-25`), the declared tools are:

```
invoke_control        (windowId, control, action, value)
invoke_action         (windowId, action, parameters)
get_window_ui_context (windowId)
```

and from `WindowingMcpManifest.json`:

```
get_window_list                  ()   "windows that can be interacted with using other tools"
get_window_ui_context via above
get_monitor_list                 ()
snap_window                      (request)
close_window                     (windowId)
get_layout_for_snappable_windows (number, monitorHandle)
```

So the OS itself now offers window enumeration, per-window UI context, and control
invocation over MCP, first-party and MIT-licensed. **It is not reachable on this build.**
`where.exe odr.exe` finds nothing; `HKLM:\SOFTWARE\Microsoft\Windows\WindowsAI` has no
properties; and Microsoft's own MCP-host quickstart states the prerequisite as *"Windows
build 26220.7262 or higher"* against this machine's `26200.9445`. The declared entry point
binary, `ShellMcpServers.Packaging.exe`, is present at
`C:\Windows\SystemApps\MicrosoftWindows.Client.Core_cw5n1h2txyewy\`, so the code is staged
and the registry front-end is what is missing. Two further gates apply even after a build
bump: the whole surface sits behind an "Experimental agentic features" toggle under
System > AI components, and ODR runs registered servers *"contained in a separate
environment"*, reached through ODR acting as an MCP proxy — with the quickstart noting an MCP
host needs *"package identity … granted to apps that are packaged using the MSIX package
format"*, a requirement *"not enforced in the public preview release but it will be in the
stable release"*. Claude Code in WSL is not an MSIX-packaged host, so even on a new enough
build this is not a `claude mcp add` line today. The docs also carry a blanket prerelease
warning: *"Some information relates to prereleased product that might change substantially
before it's commercially released."*

Record it as the thing that makes `computer-use` eventually trivial, and re-check it when the
dev's build passes 26220.7262. Note also that no first-party server exposes a browser DOM —
the browser half would still need Windows-MCP, Terminator, or `shot-scraper`.
[MCP on Windows overview](https://learn.microsoft.com/en-us/windows/ai/mcp/overview) ·
[MCP host quickstart](https://learn.microsoft.com/en-us/windows/ai/mcp/quickstart-mcp-host)

**Microsoft OmniParser v2 — hard reject, it is not a driver.** Pinned at release `v.2.0.1`
(2025-09-12), head `354021201345` (2026-07-20), 25,389 stars. It is what its own title says:
*"Screen Parsing tool for Pure Vision Based GUI Agent"* — a YOLO interactive-region detector
plus an icon-description model that *"parses user interface screenshots into structured and
easy-to-understand elements"*. It has **no input capability at all**: no click, no type, no
window handle. It is a perception component you would feed into an agent loop you wrote. It
also needs a conda environment and downloaded model weights, and the detector the README now
recommends is only available from an unmerged Hugging Face pull request. The part that does
drive a desktop is **OmniTool**, described as *"Control a Windows 11 VM with OmniParser +
your vision model of choice"* — a VM, with its own orchestration, supporting OpenAI,
DeepSeek, Qwen or Anthropic computer use. That is a competing agent stack, and it targets a
VM rather than this desktop. On a screenshot-only pipeline it is also strictly worse than
UIA for this job: UIA already returns names, roles and control patterns as structured data,
which is what OmniParser spends a GPU inferring back out of pixels.
[Repo](https://github.com/microsoft/OmniParser)

**ByteDance UI-TARS and Agent TARS — hard reject, brings its own agent.** The expected
verdict, confirmed from the README. The repo `bytedance/UI-TARS-desktop` (38,941 stars,
Apache-2.0, release `v0.3.0` of 2025-11-04, pushed 2026-09-11) describes itself as *"a
Multimodal AI Agent stack, currently shipping two projects"*: **Agent TARS**, *"a general
multimodal AI Agent stack … primarily ships with a CLI and Web UI for usage"*, and
**UI-TARS-desktop**, *"a desktop application that provides a native GUI Agent based on the
UI-TARS model"*, shipping local and remote computer operators plus browser operators. Both
halves are agents with their own model, their own loop and their own interface. The model
repo `bytedance/UI-TARS` (11,457 stars, Apache-2.0) was last pushed 2026-01-27. Nothing here
is a tool a Claude Code session calls; adopting it would mean replacing Claude Code for
desktop work, not extending it. It fails the harness column by construction, exactly as
predicted.
[Repo](https://github.com/bytedance/UI-TARS-desktop)

**Playwright over CDP — already covered, not a `computer-use` replacement.** Pinned at
`1.63.0`. It cannot see a native window at all, so it replaces at most the browser half. On
this machine it also cannot dial a Windows Chrome's debug port directly: networking mode is
`nat`, and the existing CDP research doc records that NAT has no supported path to a
loopback-bound Windows service. The workaround is the one twitch-rules-scroller already
uses, which is not really a Playwright feature — run the driver as Windows `node.exe` over
`\\wsl.localhost`. That repo also records the harder limit, from Chrome's own developer
blog: *"Chrome 136+ ignores `--remote-debugging-port` and `--remote-debugging-pipe`
entirely when launched on the default `--user-data-dir`"*, which is why its harness drives a
dedicated e2e profile on port 9333 rather than the dev's logged-in Chrome. A CDP probe
during this research returned nothing, because that e2e Chrome was not running; the two
`chrome.exe` processes `tasklist.exe` reported are the ordinary browser, which by design
refuses the debug port.

**pywinauto — reject on cost, not capability.** `0.6.9`, BSD-3-Clause, 6,162 stars, but the
last release is 2025-01-06 and the last push 2026-05-23. It is a good UIA library and it is
not an agent interface: it would need a Windows Python install, the package, and a
hand-written CLI wrapper before an agent could call it, and that wrapper is exactly the
`orca computer` shape the exit is trying to stop maintaining. Windows-MCP gets the same UIA
underneath with the wrapper already written and a protocol Claude Code already speaks.

**win32-mcp-server — reject on bus factor.** MIT, 53 tools, six of them UIA, and an
explicit security-profile system (`read_only`, `interactive`, allow/block lists, dry-run)
that is genuinely better designed than Windows-MCP's. It loses on everything else: 4 stars,
one maintainer, and a version story that does not line up — the README advertises "What's
New in v2.6", the newest GitHub release is `v2.6.1` from 2026-06-11, and PyPI's latest is
`2.5.1`. Its smart tools are also OCR-first with UIA as an attempt rather than the primary
path (`click_text` and `fill_field` "try control-based automation before OCR fallback"),
which trades determinism for coverage.

**Claude Code's built-in `computer-use` — hard reject, macOS only.** It exists and it is the
right shape: a built-in MCP server toggled from `/mcp`, landed in the CLI at v2.1.86–91.
The docs are unambiguous that it does not apply here. Under troubleshooting: *"You're on
macOS. Computer use in the CLI is not available on Linux or Windows. On Windows, use
computer use in Desktop instead."* The Desktop-versus-CLI table lists Platforms as "macOS
and Windows" for Desktop and "macOS only" for CLI. It also requires an interactive session
and is unavailable under `-p`, which would have ruled it out for dispatched workers even on
a Mac. Confirmed locally: `claude mcp list` on 2.1.269 in this WSL shell returns
`google-docs`, `exa`, `c4ai` and no `computer-use`.
[Docs](https://code.claude.com/docs/en/computer-use)

**Claude in Chrome — hard reject, one sentence.** The docs state it directly: *"Chrome
integration isn't supported in Windows Subsystem for Linux (WSL)."* Worth recording because
it is otherwise the closest fit for the browser half — it shares the real browser's login
state and drives a visible window, which is what `orca computer` was used for. If the dev
ever moves the Claude Code session to Windows-native, this becomes the browser answer and
Windows-MCP's DOM mode becomes redundant.
[Docs](https://code.claude.com/docs/en/chrome)

**Claude Desktop computer use — hard reject on the harness column.** Windows is supported
here, unlike the CLI, and the engine is the same. But it runs inside the Claude Desktop app
as its own agent session; a WSL Claude Code session cannot call it. It fails the "runs under
Claude Code rather than bringing its own agent" test by construction.
[Help centre](https://support.claude.com/en/articles/14128542-let-claude-use-your-computer-in-cowork)

**Anthropic's computer-use reference implementation — hard reject, wrong desktop.** Read at
commit `5264b72` (2026-08-21). The README describes *"the essential agent loop running
against a Linux desktop in Docker with X11 + VNC"*, shipping "a computer use agent loop
using the Claude API" and "a streamlit app for interacting with the agent loop". It controls
the container's own X11 desktop, not the Windows host, and it brings its own agent. It is a
reference for building a computer-use product, not a tool a Claude Code session invokes. The
sibling `computer-use-best-practices` quickstart runs natively but only on macOS.
[Repo](https://github.com/anthropics/claude-quickstarts/tree/main/computer-use-demo)

**Windows 365 for Agents MCP — hard reject, wrong machine.** Microsoft's official answer to
this exact question, and it is genuinely complete: `get_accessibility_tree`,
`find_ui_element`, `activate_window`, `click`, `type_text`, `press_keys`, `take_screenshot`,
plus Edge DOM tools. It drives *"a Windows 365 cloud PC"* — a provisioned cloud VM, not the
dev's desktop, and it needs a Copilot Studio / Agent 365 tenant. Its own limitation is worth
stealing as a warning: *"Browser DOM tools … operate only on the Microsoft Edge instance.
`activate_window` can focus Chrome or Firefox windows, but DOM tools don't"* — the same
browser-specific split Windows-MCP handles with its IAccessible2 fallback.
[Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-windows-365-agents)

**nut.js — hard reject, sunsetting as open source.** The GitHub repo
`nut-tree/nut.js` was last pushed **2024-05-01**, and the GitHub API reports **no license**
on it. The project's site now sells the library ("All prices include VAT where applicable")
and the changelog's latest entry, 5.2.0, is published on the commercial docs site rather
than the repo. Capability is not the problem — cross-platform mouse, keyboard, screen and
window control, with a Windows element inspector. Licence and direction are. It would also
need a Windows-side Node driver and a wrapper, same as pywinauto.

**AutoHotkey — reject, no inspection.** Not installed (`/mnt/c/Program Files/AutoHotkey`
absent), so adopting it means an install on the Windows side. It sends input well and has no
structured window-tree inspection, which is the half `orca computer` was actually used for.
Fire-and-forget input with no way to read back what happened is the worst shape for an agent
loop.

## Recommendation

**Do not retire `computer-use`. Rewrite it around Windows-MCP, with in-box PowerShell UIA
as the documented fallback.**

The reasoning, in order:

1. **The browser half is covered for rendering, not for the real window.** Correction to
   the first pass: `page-shot` and `page-eval` are absent **by design**, not missing. #691
   was rescoped and merged PR #693 deleted both scripts in favour of `shot-scraper`, which
   is installed at `~/.local/bin/shot-scraper` (`1.11`) and is what `flow/claude/CLAUDE.md`
   now names. That settles rendering. It does not settle the remaining gap: `shot-scraper`
   is headless, so it renders a URL in a browser it launches, and it cannot read the dev's
   real, logged-in, visible Chrome window. That was a distinct capability of
   `orca computer`, and nothing in the exit plan replaces it.
2. **The native half has no substitute at all.** Nothing in `page-shot`, `page-eval`,
   `shot-scraper`, or CDP can see a Windows native window. Retiring the skill would delete
   that capability outright.
3. **Windows-MCP is the laziest mechanism that holds.** Ponytail applies: it is one
   `claude mcp add` line that the vendor documents for this exact WSL topology, against a
   `uvx.exe` that is already at the documented path, over a stdio transport verified to
   cross the boundary. No wrapper to write, no CLI to version-match, no second agent.
4. **PowerShell UIA is the floor if that line ever fails.** It is already proven on this
   machine with zero install, and it covers "find the window, focus it, resize it,
   screenshot it, send keys" — enough for the common case. The skill should document it
   directly, so a broken MCP server degrades to a working Bash call rather than to nothing.
5. **Terminator is the named fallback, and Windows' own servers are the exit.** If
   Windows-MCP's `use_dom=True` disappoints on the dev's Chrome, Terminator's Chrome-extension
   route is the next thing to try — it keeps the real browser session and needs no debug port.
   It loses today on liveness and on having no documented WSL path, not on capability.
   Separately, put a dated re-check in the skill: Windows already stages first-party
   `WindowUnderstanding` and `Windowing` MCP servers on this machine, and once the build
   passes 26220.7262 and ODR is reachable by a non-MSIX host, that first-party pair should
   replace the third-party server entirely.

Shape for the rewritten skill: resolve the mechanism the way the current stub resolves the
Orca executable — prefer the `windows-mcp` MCP tools if `/mcp` shows the server connected,
fall back to `powershell.exe` UIA snippets otherwise, and hand page-only work to
`page-shot`/`page-eval` or CDP once those exist. Keep the current stub's refusal discipline:
report the exact error and stop, never silently fall through to a different mechanism.

Before adopting, decide the permission boundary. Windows-MCP's `PowerShell`, `Registry`,
`Process` and `FileSystem` tools are arbitrary Windows code execution from a WSL session,
which is a wider grant than `orca computer` held.

## Unverified

- **Windows-MCP end to end.** Nothing was installed, per the ticket's constraint. Verified:
  the documented bridge command, that `uvx.exe` sits at exactly the documented Windows path,
  and that bidirectional stdio crosses the interop boundary. Not verified: that
  `uvx windows-mcp serve` starts under `powershell.exe`, that Claude Code 2.1.269 registers
  it, or that `use_dom=True` reads the dev's Chrome. Windows Python is `3.14.4`, above the
  README's 3.13+ floor, but `uvx` provisions its own interpreter so that is not the binding
  constraint.
- **The Windows display-language prerequisite.** The README asks for English as the default
  Windows language or else disabling `App-Tool`. Not checked on this machine.
- **Whether mirrored networking would change the CDP answer.** `.wslconfig` sets only
  `memory`, `swap` and `autoMemoryReclaim`; mode is `nat`. Microsoft's docs say mirrored mode
  makes WSL `127.0.0.1` reach Windows services, which would make direct CDP viable — but
  switching networking mode is a machine-wide change with its own consequences and was not
  tested.
- **Live CDP reachability.** The e2e Chrome on port 9333 was not running, so the probe
  returned nothing rather than a measured refusal. The NAT conclusion rests on the existing
  research doc and the measured `nat` mode, not on a fresh negative.
- **`win32-mcp-server`'s PyPI/tag gap.** Observed, not explained; no maintainer statement
  found.
- **Terminator end to end.** Nothing installed. Verified: the README's Claude Code install
  line, the Windows-only support matrix, the absence of any WSL mention, the npm/tag version
  skew, and that `npx.cmd` exists on the Windows side. Not verified: that
  `powershell.exe -Command "npx.cmd -y terminator-mcp-agent"` starts a working server, or
  that its Chrome extension drives the dev's browser.
- **Windows ODR on a newer build.** The build gap is measured (`26200.9445` against the
  quickstart's `26220.7262`), the manifests and the `ShellMcpServers.Packaging.exe` binary
  were read on disk, and `odr.exe` is confirmed absent. Not verified: whether enabling
  "Experimental agentic features" on a qualifying build would let a non-MSIX WSL client reach
  these servers at all. The MSIX package-identity requirement is documented as unenforced in
  preview and enforced at stable, which suggests it would not, but no test was run and no
  qualifying build was available.
- **Whether the ODR tool list changes.** The tool names above are parsed from the
  `static_responses` block of the shipped manifests, which is the registry's cached answer to
  `tools/list`, not a live server response. The Microsoft docs carry a blanket warning that
  prerelease details "might change substantially".
- **nut.js licensing intent.** The GitHub API reports no license on the repo and the site
  sells the product. No maintainer statement was found declaring the OSS line dead, so
  "sunsetting as open source" is read off the 2024-05-01 freeze and the missing licence,
  not from an announcement.

## Sources

Primary, all read on 2026-09-12.

- [Claude Code: computer use from the CLI](https://code.claude.com/docs/en/computer-use)
- [Claude Code: Claude in Chrome](https://code.claude.com/docs/en/chrome)
- [Claude Code what's new, week 14 2026](https://code.claude.com/docs/en/whats-new/2026-w14)
- [Let Claude use your computer in Cowork](https://support.claude.com/en/articles/14128542-let-claude-use-your-computer-in-cowork)
- [Claude Platform: computer use tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
- [anthropics/claude-quickstarts computer-use-demo](https://github.com/anthropics/claude-quickstarts/tree/main/computer-use-demo)
- [CursorTouch/Windows-MCP](https://github.com/CursorTouch/Windows-MCP) and [PyPI windows-mcp](https://pypi.org/project/windows-mcp/)
- [RandyNorthrup/win32-mcp-server](https://github.com/RandyNorthrup/win32-mcp-server) and [PyPI win32-mcp-server](https://pypi.org/project/win32-mcp-server/)
- [pywinauto/pywinauto](https://github.com/pywinauto/pywinauto) and [PyPI pywinauto](https://pypi.org/project/pywinauto/)
- [nut-tree/nut.js](https://github.com/nut-tree/nut.js/) and [nutjs.dev changelog](https://nutjs.dev/changelog/core)
- [Windows 365 for Agents MCP server reference](https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-windows-365-agents)
- [MCP on Windows overview](https://learn.microsoft.com/en-us/windows/ai/mcp/overview) and [MCP host quickstart](https://learn.microsoft.com/en-us/windows/ai/mcp/quickstart-mcp-host)
- `C:\Windows\SystemApps\MicrosoftWindows.Client.Core_cw5n1h2txyewy\ShellMcpServers\Assets\*McpManifest.json` (read on disk, build 26200.9445)
- [mediar-ai/terminator](https://github.com/mediar-ai/terminator) and [npm terminator-mcp-agent](https://www.npmjs.com/package/terminator-mcp-agent)
- [microsoft/OmniParser](https://github.com/microsoft/OmniParser)
- [bytedance/UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop) and [bytedance/UI-TARS](https://github.com/bytedance/UI-TARS)
- `gh pr view 693` / `gh issue view 691` (the `page-shot` rescope to `shot-scraper`)
- `~/src/twitch-rules-scroller/docs/research/cdp-real-chrome.md`, `AGENTS.md`, `e2e.sh`, `e2e/chrome-windows.mjs`
- `~/.agents/skills/computer-use/SKILL.md`
