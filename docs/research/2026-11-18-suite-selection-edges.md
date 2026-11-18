# Suite selection: the edges removed and the new replay (#1955)

Records what `tests/suite-edges.py` stopped treating as an edge, and the replay
that measures the result. The survey this answers is
`2026-11-17-pr-test-cost-survey.md`; the old finder is the one in git history
before #1955.

## What changed

| Before | After |
| --- | --- |
| An edge linked two **top-level directories**: any change under `X/` ran every suite of `D/` once one file of `D/` mentioned `X/`. | An edge links a source **file** to the **file** it reaches (`b/lib.py -> a/x.txt`). A change to `a/other.txt` no longer runs `b/`. |
| Edges closed transitively over directories, so `flow`, `implement`, `implement-spec`, `docs` and `multi-axis-code-review` formed one cluster. | The closure runs over files; suites run for the directories of the files in the closure. |
| A comment, a docstring or a `git commit -m` message could make an edge. | Those are blanked before matching. |
| A path that names nothing tracked (a path in a fixture repo, a file written at run time) fell back to the whole directory. | It is no edge. A bare directory with no path after it is still every file under it. |
| A directory put on `sys.path` reached every file in it. | It reaches the modules the file imports from it. |
| A Markdown file in a directory with no suites ran the full seam. | A diff of only such files runs the suites marked `# all.sh: prose-check`, the repo-wide suites, and the suites of any directory that reaches the file. |
| A source file that names a file beside it (or below it) by its written name (`helper.py` reading `"x.txt"`) had no edge to it. | It does, so a change to `x.txt` reaches the suites that load `helper.py`. |
| An unknown file type was treated as its directory. | It runs the full seam, as do a change to `tests/all.sh` or `tests/suite-edges.py`. |
| An empty or failed answer from the finder was checked by line count. | The finder prints a verdict line (`full`, `dirs <list>` or `prose <list>`); a missing line, an unknown word, a missing tab or a non-zero exit runs the full seam and says so. |

## Edges removed

The old finder made 153 links from a source file to a top-level directory. 11
are gone; the other 142 stay as links to the files they name (837 file edges
between directories, against whole directories before). Each removed link, with
the reason it was false:

| Source | Directory | Line | Why it was false |
| --- | --- | --- | --- |
| `drain/drain_test.py:1163` | `test-audit/` | `sb.git(sb.repo, "commit", "-qm", "root lockfile")` | The text is a commit message; `root` set off the hint and `test-audit` came from the surrounding lines. |
| `flow/lane/src/git_origin.rs:87` | `tests/` | `#[path = "../tests/support/identity.rs"]` | The path is relative to `flow/lane/src`, so it names `flow/lane/tests/`, not the top-level `tests/`; no such file exists at the top. |
| `implement-spec/closure_test.py:92` | `docs/` | `"examples/thermo/component.js": "#include ../_shared/line-kind.js\n"` | A file written into a fixture repository. |
| `implement-spec/frontier.py:43` | `docs/` | `# /wayfinder child (docs/agents/issue-tracker.md), ...` | A comment. |
| `implement-spec/loop_test.py:272` | `docs/` | `# under it; a mere shared parent directory holds nothing (#1695).` | A comment; `docs` was found in the lines after it. |
| `implement/codex-audit.py:59` | `research/` | `TRIAL = HERE.parent / "docs" / "research" / "2026-09-14-..."` | `research` is a path component under `docs/`, not the top-level `research/`. |
| `implement/stale_refs_test.py:119` | `docs/` | `root = repo({"implement/pre-gate.sh": "echo gate\n", ...` | Files written into a fixture repository. |
| `tests/fixture-identity-sites.test.sh:30` | `docs/` | `scan() { # <repo root>: tracked, non-Markdown files outside docs/ ...` | A comment on a shell function. |
| `tests/retired_name_test.py:79` | `implement-spec/` | `root = repo({"implement-spec/retire_landing.py": ...` | A file written into a fixture repository. |
| `tests/review_cache_e2e_test.py:40` | `research/` | `MACR = ROOT / "multi-axis-code-review"` | `research` came from a later line of the three-line span, where it is a path under `docs/`. |
| `tests/spec_1730_e2e_test.py:302` | `implement/` | `assert not (ROOT / "implement" / "gitcmd.py").exists()` | The test asserts the file is absent; there is nothing to load. |

The narrowed links, by example: `backstop/backstop.py` reached all of `flow/`
(141 files) and now reaches `flow/bin/notify-send` and its test;
`multi-axis-code-review/review_ledger.py` reached the 125 files of `docs/` and
now reaches the modules it imports from `docs/research`.

`python3 tests/suite-edges.py --edges` prints every current edge with its
source line.

## Replay

`python3 tests/replay_selection.py --prs 60` replays the last 60 squash-merged
PRs on `origin/main` through `tests/all.sh --list --files`, against the tree it
is run in. Nothing is run.

Result on 2026-11-18, 156 suites in the tree: **mean 90.8 suites per PR** (the
survey's replay of the old rules: 132.7 of 153). 14 PRs select every suite and
16 select 130 or more (survey: 12 and 44 or more). The 14 full runs are
legitimate widenings: PRs that change `tests/all.sh`, a root file such as
`.gitignore`, or a file type the selector does not know (`justfile`), plus
sweeps that touch most directories at once. The floor for a narrowed run that is not
Markdown-only is the 29 suites under `tests/` and the repo-wide ones; a
Markdown-only diff in directories with no suites runs fewer (the prose checks
and the repo-wide ones).
