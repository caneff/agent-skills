---
name: setup-peacock-color
description: Set a VS Code Peacock window color for the current repo — writes .vscode/settings.json with a base color plus all derived activity/status/title-bar customizations. Shows an interactive color picker artifact, or accepts a hex/color name directly. Use when the user wants to color/theme a VS Code window per-repo, mentions Peacock, or says "give this repo a color".
when_to_use: When the user wants to set or change the Peacock color of a repo's VS Code window. Especially in WSL/SSH/remote windows, where the peacock.remoteColor key is required and easy to forget.
---

# setup-peacock-color

Give a repo its own VS Code window color via Peacock, correctly, the first time.

## The one thing that breaks it

Peacock watches `.vscode/settings.json`. On any save where its active color
doesn't match, it **strips** `workbench.colorCustomizations`. In a **remote
window (WSL / SSH / dev container)** the active color comes from
`peacock.remoteColor`, NOT `peacock.color`. Omit `remoteColor` and every edit
gets wiped on the next save. So: always write BOTH keys.

## Steps

1. **Get the base color.**
   - If the user already gave a hex or a named color (e.g. "Dracula purple",
     "#9580ff"), use it — skip the picker.
   - Otherwise show the picker: render `picker.html` in this skill's directory
     with the Artifact tool, then ask the user to read back the hex it shows.

2. **Derive the full color set** (deterministic — don't hand-eyeball shades):

   ```bash
   uv run <skill_dir>/derive.py "#RRGGBB"
   ```

   Prints the complete settings fragment (peacock.color, peacock.remoteColor,
   showColorInStatusBar, and all `workbench.colorCustomizations`).

3. **Write it into the repo.**
   - Target: `<repo>/.vscode/settings.json`.
   - If the file has other settings, MERGE — replace only the `peacock.*` and
     `workbench.colorCustomizations` keys, keep the rest. If it's absent or only
     has Peacock keys, overwrite.

4. **Tell the user to reload:** Command Palette → "Developer: Reload Window".
   Peacock will keep the colors (it may re-derive its own tints from the base —
   that's expected and fine).

## Notes

- Remote windows are the default assumption here (this setup lives in WSL).
  Writing `remoteColor` on a local window is harmless, so always write it.
- `derive.py --demo` self-checks the contrast + remoteColor logic.
- Don't touch global User settings — Peacock color is intentionally per-repo.
