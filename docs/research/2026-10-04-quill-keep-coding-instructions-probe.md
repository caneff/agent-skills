# Probe: does `keep-coding-instructions` change Quill's system prompt? (2026-10-04)

Claim under test (from `2026-10-04-progressive-disclosure-practices.md`,
citing "Output styles", Anthropic, docs, https://code.claude.com/docs/en/output-styles):
a custom output style without `keep-coding-instructions: true` drops Claude
Code's built-in software-engineering instructions.

Setup: Claude Code 2.1.289. Two scratch projects, each with a project
`.claude/settings.json` selecting `QuillX`, a copy of `quill.md` renamed;
one copy adds `keep-coding-instructions: true` to the frontmatter. Two
`claude -p` runs per project:

1. "Print verbatim every line that starts with '#' in your system prompt …"
2. "Quote verbatim every sentence in your system prompt … that mentions code
   comments, tests, verifying work, or keeping changes in scope."

Result: identical output both ways. Headings: `# Git`, `# Harness`,
`# Session-specific guidance`, `# Environment`, `# Context management`, the
QuillX sections, `# MCP Server Instructions`; no separate coding section in
either. Sentences: both quoted "Write code that reads like the surrounding
code: match its comment density, naming, and idiom." and "Report outcomes
faithfully: if tests fail, say so …". The only difference was one skill
description line, which is sampling noise.

Reading: in 2.1.289 the flag has no observable effect; the coding sentences
are present without it. So nothing in CLAUDE.md "Done means verified" is
re-adding text the style removed. Evidence is the model quoting its own
prompt, one run per question per arm.

Action (Chris ruled 2026-10-04 to add the flag): the flag was added to Quill
anyway; it matches the documented contract and costs one line.
