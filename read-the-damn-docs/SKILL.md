---
name: read-the-damn-docs
description: >-
  Use when installing or upgrading a version-sensitive package, SDK, or
  framework; working with auth, billing, migrations, or another
  security-sensitive flow; or diagnosing an error that suggests API drift
  (deprecation, missing exports, changed defaults, version mismatch).
  Web-searches for current official docs and reads them before assuming from
  memory. For Anthropic/Claude API questions, defer to the claude-api skill
  instead.
---

# Read The Damn Docs

Do not guess where authoritative docs can answer the question. Web-search for
the current official docs, open the relevant pages, and read them before
coding.

**Anthropic or Claude API questions go to the `claude-api` skill**, not this
one — it already carries current model IDs, pricing, and API specifics.

## Docs-First Triggers

Read docs before proceeding when any of these are true:

- **Version-sensitive install/upgrade.** Adding, upgrading, or configuring a
  package, SDK, framework, plugin, or CLI. Check the current version first
  (`npm view <pkg> version` or the ecosystem equivalent), then read the docs
  for that version before writing imports, config, or install commands.
- **Auth, billing, migration, or security-sensitive flow.** OAuth scopes,
  permissions, secrets, webhooks, payments, PII, encryption, data retention,
  database migrations, or compliance. Ground the implementation in what the
  provider's or framework's docs actually say.
- **Error suggesting API drift.** Deprecation warnings, unknown options,
  missing exports, invalid config, unsupported fields, or a changed default.
  Read the migration guide or changelog for the installed version before
  patching around the symptom.

## What Counts As Docs

Use the most authoritative source available:

- Official product docs, API references, migration guides, changelogs, and
  SDK source/types for third-party behavior. Find these with web search when
  you do not already have the exact URL.
- Package registry metadata for versions.
- Local repo docs, ADRs, and schemas when the question is about
  project-specific behavior rather than a third-party contract.

Avoid Stack Overflow, old blog posts, and memory as the primary source when
official docs exist.

## Required Workflow

1. Identify the exact surface: package name, installed version, target
   version, provider endpoint, or config file.
2. Search the web for the current official docs unless they're already local
   or the user supplied a URL.
3. Open and read the docs closest to that surface.
4. Extract the facts needed: option names, imports, breaking changes, limits,
   permissions, examples for the current major version.
5. Implement or answer using those facts. If the docs conflict with existing
   code, inspect the local code path and call out the discrepancy.
6. Verify with the smallest useful check: typecheck, tests, build, or a local
   reproduction.
7. Name the docs consulted when that evidence affects the recommendation.

## If Docs Are Unavailable

If network access, auth, or missing local files prevents reading the docs,
say that plainly before relying on memory.
