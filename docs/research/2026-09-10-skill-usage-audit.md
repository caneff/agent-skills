# Skill usage audit

Read-only audit completed on 2026-09-10. The scan found 83 skills and examined
3,445 Claude transcript files. Counts are distinct transcript files containing
an exact `"skill":"<name>"` invocation; `NEVER` means none in retained history.

| Skill | Sessions | Last used | Verdict | Reasoning |
|---|---:|---|---|---|
| add-molab-badge | 0 | NEVER | merge-into-marimo-notebook | A narrowly scoped marimo-adjacent documentation action. |
| all-audits | 0 | NEVER | keep | A distinct whole-repo audit-sweep workflow. |
| anywidget-generator | 0 | NEVER | merge-into-marimo-notebook | An implementation mode for notebook work, not a separate trigger. |
| ask-matt | 0 | NEVER | retire | A generic skill router adds no durable task capability. |
| audit-instructions | 2 | 2026-08-21 | keep | Specific instruction-quality audit with demonstrated use. |
| auto-paper-demo | 0 | NEVER | merge-into-implement-paper-auto | Same automatic paper-to-notebook outcome. |
| burndown | 0 | NEVER | merge-into-implement-spec | Both execute a ticket/spec frontier through supervised workers. |
| codebase-design | 10 | 2026-09-07 | keep | Frequently used design vocabulary and interface-improvement method. |
| comment-audit | 2 | 2026-08-21 | keep | A focused code-quality audit, not duplicated by another skill. |
| computer-use | 7 | 2026-09-10 | keep | Distinct OS-level interaction capability. |
| crap-audit | 0 | NEVER | keep | CRAP scoring is a uniquely measurable test-risk audit. |
| create-lmd-page | 0 | NEVER | keep | A precise, externally constrained publishing workflow. |
| dead-code | 1 | 2026-08-21 | keep | Narrow static-analysis question with a useful, distinct result. |
| diagnosing-bugs | 7 | 2026-09-06 | keep | Frequently used diagnosis loop. |
| docstring-coverage | 1 | 2026-08-21 | keep | Specific public-API documentation audit. |
| domain-drift | 2 | 2026-08-21 | keep | Complements domain modeling by auditing terminology in code. |
| domain-modeling | 28 | 2026-09-09 | keep | High use and a clear core modeling role. |
| duplication | 1 | 2026-08-21 | keep | Focused semantic-duplication audit. |
| error-handling | 1 | 2026-08-21 | keep | Focused swallowed-error audit. |
| extract-coding-standards | 0 | NEVER | keep | A distinct history-mining workflow for team conventions. |
| file-ticket | 7 | 2026-09-10 | keep | Clear one-shot issue-capture trigger. |
| find-skills | 0 | NEVER | keep | Distinct discovery workflow for external skills. |
| grill-me | 1 | 2026-09-03 | merge-into-grilling | Same stress-test/interview trigger. |
| grill-with-docs | 0 | NEVER | merge-into-grilling | Grilling with an optional documentation-output mode. |
| grilling | 96 | 2026-09-09 | keep | Strongest usage signal in the catalog. |
| handoff | 0 | NEVER | keep | Distinct session-transition workflow. |
| humanizer | 0 | NEVER | retire | Generic rewriting task with no observed demand. |
| implement-paper-auto | 0 | NEVER | merge-into-implement-paper | Automatic execution can be a mode of the paper workflow. |
| implement-paper | 0 | NEVER | keep | A specialized research-paper exploration workflow. |
| implement-spec | 0 | NEVER | keep | Distinct spec-driven worker orchestration. |
| implement | 92 | 2026-09-09 | keep | High-use general implementation flow. |
| improve-codebase-architecture | 3 | 2026-08-23 | merge-into-codebase-design | Both identify and act on deep-module/design improvements. |
| jupyter-to-marimo | 0 | NEVER | merge-into-marimo-notebook | Conversion is one notebook-authoring entry path. |
| landed | 1 | 2026-08-30 | keep | Distinct recent-work review outcome. |
| loop-me | 0 | NEVER | merge-into-grilling | A workspace-specific variant of the grilling flow. |
| marimo-batch | 0 | NEVER | merge-into-marimo-notebook | Scheduling preparation is a notebook lifecycle mode. |
| marimo-notebook | 0 | NEVER | keep | Core notebook-authoring capability. |
| marimo-pair | 0 | NEVER | keep | Live-session pairing is distinct from file authoring. |
| migrate-to-shoehorn | 0 | NEVER | retire | One library-specific migration has no observed demand. |
| mutation-audit | 0 | NEVER | keep | Mutation testing answers a materially different test-quality question. |
| orca-cli | 7 | 2026-09-09 | keep | Frequently used operational interface. |
| orchestration | 0 | NEVER | merge-into-orca-cli | Its operational triggers substantially overlap Orca CLI usage. |
| pickup | 0 | NEVER | merge-into-handoff | The counterpart resume step belongs in the handoff workflow. |
| ponytail-audit | 3 | 2026-08-23 | keep | Distinct whole-repo simplification/overengineering review. |
| prompt-master | 0 | NEVER | retire | Generic prompt-writing capability has no usage signal. |
| prototype | 7 | 2026-09-03 | keep | Clear, recurring design-validation use case. |
| python-testing-patterns | 1 | 2026-08-22 | keep | Focused Python test-quality guidance. |
| read-the-damn-docs | 0 | NEVER | keep | High-value guardrail for version-sensitive and security-sensitive work. |
| research | 20 | 2026-09-08 | keep | High use and a clear primary-source research role. |
| resolving-merge-conflicts | 10 | 2026-09-06 | keep | High-use, distinct recovery workflow. |
| scaffold-exercises | 0 | NEVER | retire | Narrow scaffolding task without retained usage. |
| setup-matt-pocock-skills | 1 | 2026-08-13 | keep | Deliberately one-time foundational setup. |
| setup-peacock-color | 0 | NEVER | retire | Cosmetic, one-file setup does not warrant a standalone skill. |
| setup-pre-commit | 0 | NEVER | retire | Generic setup work without retained demand. |
| setup-python-repo | 0 | NEVER | keep | A substantial, opinionated bootstrap workflow. |
| setup-ts-deep-modules | 0 | NEVER | merge-into-codebase-design | Tool setup is an implementation branch of the design method. |
| skill-audit | 0 | NEVER | keep | Retained logs predate this invocation; it provides a distinct maintenance audit. |
| skills-safe-update | 0 | NEVER | keep | A specialized, safety-sensitive update workflow. |
| skills-sync | 0 | NEVER | keep | A distinct synchronization/repair operation. |
| sm-link | 4 | 2026-09-09 | keep | Specialized SudokuMaker link tooling with recent use. |
| streamlit-to-marimo | 0 | NEVER | merge-into-marimo-notebook | Conversion is another notebook-authoring entry path. |
| tdd | 179 | 2026-09-09 | keep | Most-used implementation-quality workflow. |
| teach | 0 | NEVER | keep | User education is a distinct outcome. |
| test-audit | 2 | 2026-08-21 | keep | Broad test-value review, complementary to mutation testing. |
| thermo-nuclear-code-quality-review | 3 | 2026-08-23 | merge-into-ponytail-audit | Both target maintainability and overengineered structure. |
| to-questionnaire | 0 | NEVER | retire | Generic question-generation does not need a separate skill. |
| to-spec | 34 | 2026-09-09 | keep | Strong usage and a clear synthesis-to-spec outcome. |
| to-tickets | 23 | 2026-09-09 | keep | Strong usage and a distinct decomposition-to-tracker outcome. |
| triage | 0 | NEVER | keep | Defined issue-state workflow, despite no retained invocation. |
| two-axis-code-review | 28 | 2026-09-10 | keep | High-use, purposefully scoped review method. |
| type-tightness | 1 | 2026-08-21 | keep | Focused type-quality audit. |
| visual-plan | 0 | NEVER | keep | Distinct visual planning deliverable. |
| visual-recap | 1 | 2026-08-15 | keep | Distinct visual review/recap deliverable. |
| visual-teach | 2 | 2026-09-08 | keep | Shared visual teaching/reporting foundation. |
| wait-what | 22 | 2026-09-10 | keep | Frequently used conversation-repair action. |
| wasm-compatibility | 0 | NEVER | merge-into-marimo-notebook | Compatibility checking is a notebook delivery mode. |
| wayfinder | 11 | 2026-09-06 | keep | Distinct large-program planning workflow. |
| wizard | 0 | NEVER | retire | Generic shell-wizard generation has no retained use. |
| writing-beats | 0 | NEVER | merge-into-writing-shape | Both are stages of the same long-form writing workflow. |
| writing-for-agents | 7 | 2026-09-02 | keep | Clear, recurring agent-documentation use case. |
| writing-fragments | 0 | NEVER | merge-into-writing-shape | Raw-material exploration can be a mode of the writing workflow. |
| writing-shape | 0 | NEVER | keep | Best canonical home for the consolidated writing workflow. |
| ww | 9 | 2026-09-03 | merge-into-wait-what | It is explicitly an alias of `wait-what`. |

No files were modified during the audit itself.
