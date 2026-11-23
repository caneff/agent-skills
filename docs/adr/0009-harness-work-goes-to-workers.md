# Harness work goes to auto-mode workers

Status: accepted, 2026-11-23 (ruled by Chris)

On 2026-10-04 (8b068e85) we kept all harness work (settings, hooks, mods,
plugins) away from auto-mode workers. At that time the must-name `soft_deny`
rules (`Self-Modification`, `Auto-Mode Bypass`, `Instruction Poisoning`,
`Unauthorized Persistence`) parked a worker at every step, and no
`autoMode.allow` entry could clear them. On 2026-10-09 (b7908905) Chris
allowed self-modification, and those rules have since left the live
`soft_deny` list. The rule stayed anyway, so 13 of the 16 `ready-for-human`
tickets on 2026-11-23 were there only because of it.

Harness work now takes the code lane like any other code. Two kinds of
ticket stay `ready-for-human`: those whose proof needs a live session or
Chris's eye, and work outside any repo, such as the user crontab.

The remaining risk is that a merged hook entry goes live at once, because
`~/.claude/settings.json` links into `main` (#1942). Reverting the merge
undoes it.
