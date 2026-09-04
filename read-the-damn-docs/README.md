# read-the-damn-docs

Make agents web-search for the docs before they guess.

A docs-first discipline skill, scoped to three trigger branches: version-sensitive
package installs/upgrades, auth/billing/migration/security-sensitive flows, and
errors that suggest API drift. Anthropic/Claude API questions defer to the
`claude-api` skill instead — see `SKILL.md`.

Forked from [BuilderIO/skills](https://github.com/BuilderIO/skills)'s
`read-the-damn-docs`; tracked in `.extra-skills.json` at the repo root.
