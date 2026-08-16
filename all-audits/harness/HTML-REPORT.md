# HTML Report Harness — asset delivery and scaffold

Every audit that renders a visual-teach HTML report — `ponytail-audit`,
`thermo-nuclear-code-quality-review`, `improve-codebase-architecture`, and the
grouped-summary audits (`test-audit`, `comment-audit`) via
[`findings-schema.md`](findings-schema.md) — shares one render mechanism: copy
the `vt-*` assets beside the report and link them relatively, follow the same
scaffold rules, and get the same theme toggle for free. This doc pins that
shared mechanism only. Each skill's own `HTML-REPORT.md` covers what is
actually specific to it: header/verdict shape, badge vocabulary, card
anatomy, diagram patterns, and tone.

The report is a single self-contained HTML file in the OS temp directory,
styled with the **visual-teach** design system — the same vendored `vt-*`
components and `--vt-*` theme tokens across every audit. It opens offline,
carries a working light/dark mode, and loads no external host.

## Asset delivery — copy alongside at render time

The report renders to the OS temp dir, so it cannot relative-reference the
skills folder. **Copy the assets the report uses next to the report at render
time and link them relatively.** Do not inline them, and do not point at a
remote host.

The visual-teach assets live in the visual-teach skill's `assets/` folder
(`~/.agents/skills/visual-teach/assets/` in this setup — resolve it once and
reuse). Copy only what the report uses — never KaTeX:

- `base/base.css` + `base/base.js` — the spine: page shell, prose, the
  dark-mode token layer, the theme toggle. Always copy both.
- `components/<name>/<name>.css` — one per component used (a report typically
  reaches for `callout`, `chip`, `code`, and `diagram`). Copy
  `components/code/code.js` too — it drives the copy buttons and
  highlighting.
- `prism/` grammars — for highlighted before/after source: `prism-core.min.js`,
  `prism-clike.min.js`, and one grammar per language shown (e.g.
  `prism-python.min.js`). Only if code is highlighted.
- `mermaid.js` + `mermaid.min.js` — only if a card uses a Mermaid diagram. The
  bridge (`mermaid.js`) loads the library from the file beside it, so copy
  both together.

Sketch of the render step:

```sh
vt="$HOME/.agents/skills/visual-teach/assets"                                  # resolve the visual-teach assets once
tmp="${TMPDIR:-/tmp}/<skill>-$(date +%s)"
mkdir -p "$tmp/assets/prism" "$tmp/assets/components"
cp -R "$vt/base" "$tmp/assets/"                                                # the spine (base.css + base.js)
for c in callout chip code diagram; do                                        # only the components used
  cp -R "$vt/components/$c" "$tmp/assets/components/"
done
cp "$vt/prism/prism-core.min.js" "$vt/prism/prism-clike.min.js" "$tmp/assets/prism/"
cp "$vt/prism/prism-python.min.js" "$tmp/assets/prism/"                        # one grammar per language shown
# cp "$vt/mermaid.js" "$vt/mermaid.min.js" "$tmp/assets/"                      # only with a diagram
# write the report to "$tmp/report.html" linking href="assets/base/base.css" etc.
```

The tmp dir already resolves `${TMPDIR:-/tmp}` — a skill reusing this pattern
names its own folder (`<tmpdir>/<skill>-<timestamp>/report.html`) and needs no
separate fallback note. Once the report is written, **open it and hand off the
path**: `xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on
Windows, then tell the user the absolute path.

## Scaffold basics

`<!doctype html>` on line 1 is required. Link `base/base.css` and each
component's CSS in the `<head>`; load Prism grammars **before** `base.js` /
`code.js` so their auto-init can highlight code; add the `mermaid.js` bridge
last (only if used).

> **Never add `type="module"` to `base.js`, `code.js`, or the `mermaid.js`
> tag.** They are plain scripts; `type="module"` makes the browser load them
> under CORS rules, which `file://` blocks — the toggle, copy buttons, and
> Prism then silently die.

The theme toggle and dark mode need no code of yours: `base/base.css` holds
the `--vt-*` token layer (light `:root`, a `prefers-color-scheme` dark block,
and a `[data-theme]` override) and `base/base.js` injects a fixed toggle that
flips `data-theme`. The default view follows the OS theme; the toggle forces
either. Mermaid re-themes on the flip through the bridge.

## Beyond this doc

This harness stops at the mechanism. For header/verdict shape, badge
vocabulary, card anatomy, diagram patterns, and tone — read the skill's own
`HTML-REPORT.md`:

- [`ponytail-audit/HTML-REPORT.md`](../../ponytail-audit/HTML-REPORT.md)
- [`thermo-nuclear-code-quality-review/HTML-REPORT.md`](../../thermo-nuclear-code-quality-review/HTML-REPORT.md)
- [`improve-codebase-architecture/HTML-REPORT.md`](../../improve-codebase-architecture/HTML-REPORT.md)

For the grouped-summary shape used by `test-audit` and `comment-audit`, see
[`findings-schema.md`](findings-schema.md).
