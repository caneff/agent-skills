# HTML Report Harness — the shell, and where the body goes

Every audit that renders a visual-teach HTML report — a full card-per-finding
audit (e.g. `ponytail-audit`, `thermo-nuclear-code-quality-review`,
`improve-codebase-architecture`) or any audit writing `findings.jsonl` for a
grouped summary via [`findings-schema.md`](findings-schema.md) — renders the
same document. One module owns it, so no skill describes the `<head>`, the
`<main>` wrapper, or asset copying again.

## The renderer — `pagelib.py`

- `page(title, kicker, h1, lede, body, *, prefix="", extra_css="")` returns the
  whole document: doctype, the head linking `base/base.css`,
  `components/callout/callout.css` and `base/base.js`, and a `<main>` holding
  kicker / h1 / lede / your body HTML. `prefix` reaches `assets/` from a page
  in a subfolder; `extra_css` is the page's own `<style>`.
- `copy_assets(dest, components=("callout",))` copies visual-teach's
  `base/` and each named component into `dest/assets/`, replacing what is
  there — call it once beside the page you wrote, so the relative links
  resolve.

A report that highlights code or draws a Mermaid diagram needs two files
`copy_assets` does not carry: copy `prism/prism-core.min.js`,
`prism-clike.min.js` and one grammar per language beside the page, and
`mermaid.js` + `mermaid.min.js` together when a card uses a diagram. Load
Prism grammars **before** `base.js` / `code.js`, and add the `mermaid.js`
bridge last.

> **Never add `type="module"`** to `base.js`, `code.js`, or the `mermaid.js`
> tag. They are plain scripts; `type="module"` makes the browser load them
> under CORS rules, which `file://` blocks — the toggle, copy buttons, and
> Prism then silently die.

The report is a single self-contained HTML file in the OS temp directory. It
opens offline, carries a working light/dark mode, and loads no external host.
The tmp dir resolves `${TMPDIR:-/tmp}` — a skill names its own folder
(`<tmpdir>/<skill>-<timestamp>/report.html`) and needs no separate fallback
note. Once the report is written, **open it and hand off the path**:
`xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on
Windows, then tell the user the absolute path.

**Inside a sweep, write the manifest.** When the prompt names a manifest
path, `driver.py` finds your report there — a JSON object naming
`report_path`, not a stdout scan. See
[`AUDIT-RUN.md`](AUDIT-RUN.md#the-manifest-559)'s "The manifest" section for
the exact shape.

## Beyond this doc

This harness stops at the shell. For header/verdict shape, badge vocabulary,
card anatomy, diagram patterns, and tone — read the skill's own
`HTML-REPORT.md`:

- [`ponytail-audit/HTML-REPORT.md`](../../ponytail-audit/HTML-REPORT.md)
- [`thermo-nuclear-code-quality-review/HTML-REPORT.md`](../../thermo-nuclear-code-quality-review/HTML-REPORT.md)
- [`improve-codebase-architecture/HTML-REPORT.md`](../../improve-codebase-architecture/HTML-REPORT.md)

For the grouped-summary shape used by any audit writing `findings.jsonl`, see
[`findings-schema.md`](findings-schema.md).
