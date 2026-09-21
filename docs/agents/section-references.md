# Section references

A cross-reference to a heading in Markdown prose is written `§ <Heading>`.
`tests/check-section-references.py` checks every tracked Markdown file except
`docs/research/` and `tests/fixtures/`, and fails the suite on a reference that
does not resolve.

## Which file a reference points at

- A `.md` path on the same line names the target; the last one that resolves
  wins. Paths resolve against the source file's directory, then the repo root;
  `~/.agents/skills/` maps to the repo root; an absolute path must be a
  tracked file.
- "this file" on the line targets the file the line is in, and overrides any
  path on the line.
- "of that file" after the `§` targets the last file named on an earlier line.
- With no path on the line that resolves (a mistyped or untracked path counts
  as none), the reference targets its own file. If the previous line named
  another file, a bare `§` is a collision and fails: name a tracked file on
  the same line.

## The name

- The name starts with a letter or digit right after the whitespace that
  follows the section sign. Anything else (bold, quotes, underscores) is not
  matched, so the reference is silently unchecked: write the plain heading.
- The name runs from the section sign to the first of `. , ; : ! ? ) } ]`, a
  `'s`, or another section sign; a trailing ` and` is dropped. It is capped at
  about 160 characters. Write the heading, then punctuation.
- A heading only has to start with the name, so a reference reading "The merge"
  matches a heading "The merge: who and when". Use enough words to be
  unambiguous. Matching ignores trailing punctuation and repeated whitespace.
- A bare number after the section sign matches a heading that starts with that
  number and a period.

## The step locator

`§ <Heading> step <n>` names the section `<Heading>` and its numbered step
`<n>`; the locator and whatever follows it are not part of the name. The
forms the checker reads, all case-insensitive:

- `step` or `steps`, then a number, or a spelled-out number from one to ten:
  `§ The merge step 3`, `§ The merge Step three`.
- A range with a hyphen, en dash or em dash: `§ Before the PR steps 3-5`. It
  must ascend; `steps 5-3` fails.
- An optional colon between the name and the locator: `§ Before the PR: step 6`.
- The name holds no punctuation. `§ Build: deployment step 3` is read as the
  heading `Build: deployment` with step 3 required, not as `Build` with no
  step; a name the locator cannot read that way fails rather than dropping
  the step.

Every step named must exist in the target section as a `<n>.` or `<n>)` list
item or a `Step <n>` sub-heading. Fenced code is ignored: a fence closes only
on its own character, at least as long as the one that opened it, with
nothing after it, so a `~~~` inside a longer backtick fence is text, and a
numbered line inside any fence is not a step.

A heading that is itself `Step 3` keeps only `Step 3` as its label, so
`§ Step 3 and then prose` resolves to that heading and the prose does not
join the name (fixture `step-heading-prose-valid`). Whatever the name, put
punctuation right after it.

Known limits: a spelled-out number above ten is not recognised; a second
locator in one pointer (`step 3 and step 9`) is not read; a lazily numbered
list (`1.` on every item) does not satisfy the check; and a step can resolve
in a sibling heading that shares the name's prefix (#990).
