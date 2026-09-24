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
  `'s`, another section sign, or a backtick (the close of a code span); a
  trailing ` and` is dropped. It has no length cap: with none of those, it
  runs to the end of the line. Write the heading, then punctuation. A
  heading whose name holds a code span cannot be referenced: a name cut at a
  backtick outside a wrapping code span fails, saying inline code in a
  heading name is unsupported. Write the plain heading. A code span is
  recognised by CommonMark's own rule — a backtick run opens it and only a
  later run of the same length closes it, in the same paragraph — so a name
  wrapped in a single backtick pair or a double one is read as inside the
  span either way (write `<sign> Build` inside one backtick, or inside two).
  A span may cross a line break, but a paragraph ends at a blank line and at
  the start of a list item. Inside a list (a paragraph that starts on a
  marker or indented) any marker starts the next item; in other prose only
  a bullet with text after it, or an item numbered 1, does, so a wrapped
  line reading `2. ...` continues the paragraph. A
  heading, and each row of a table (a header row with a `| --- |` delimiter
  row under it, down to the next blank line, heading or fence), is a
  paragraph of its own line; a `|` line with no delimiter row is ordinary
  text. A line inside a fence, markers included, is code throughout. The
  guard against inline code runs on the name before the possessive or conjunction trimmer
  touches it, not after: `<sign> Build's` immediately followed by a code
  span, or `<sign> Build and` immediately followed by one, both fail rather
  than silently downgrading to a reference to an unrelated `Build` heading.
  A step locator (below) ending the name well before the backtick is not
  this case — that is the locator's own boundary, and the rest of the
  sentence is ordinary prose.
- **The sign as a word.** Every section sign followed by a name is a
  reference, so a sentence that uses the sign as a word fails as a missing
  heading. Prefer rewording ("the Liveness section"). To keep the sign,
  write it with a backslash before it and the checker never reads it; the
  backslash is not a Markdown escape for this character, so it shows in
  rendered pages. The sign alone in backticks, or followed by no name, is
  not read either. Inside this doc, `<sign>` (defined under The step
  locator) is the placeholder for a sign that must not be read.
- A heading only has to start with the name, so a reference reading "The merge"
  matches a heading "The merge: who and when". Matching ignores trailing
  punctuation and repeated whitespace. An exact normalized match wins over
  any number of headings that only share the name's prefix — a step
  required in "Merge" is checked against "Merge" even when a sibling
  "Merge notes" also holds that step number (#990). With no exact match, a
  single prefix match is the answer; more than one fails, naming every
  heading it could mean. Use enough words to be unambiguous.
- A bare number after the section sign matches a heading that starts with that
  number and a period.

## The step locator

`§ <Heading> step <n>` names the section `<Heading>` and its numbered step
`<n>`; the locator and whatever follows it are not part of the name. The
forms the checker reads, all case-insensitive:

In the examples below `<sign>` stands for the section sign, which the
checker would otherwise read as a live reference.

- `step` or `steps`, then a number, or a spelled-out number from one to ten:
  `<sign> The merge step 3`, `<sign> The merge Step three`.
- A range with a hyphen, en dash or em dash: `<sign> Before the PR steps 3-5`. It
  must ascend; `steps 5-3` fails.
- An optional colon between the name and the locator: `<sign> Before the PR: step 6`.
- The name holds no punctuation. `<sign> Build: deployment step 3` is read as the
  heading `Build: deployment` with step 3 required, not as `Build` with no
  step; a name the locator cannot read that way fails rather than dropping
  the step.

Every step named must exist in the target section as a `<n>.` or `<n>)` list
item or a `Step <n>` sub-heading. Fenced code is ignored: a fence closes only
on its own character, at least as long as the one that opened it, with
nothing after it, so a `~~~` inside a longer backtick fence is text, and a
numbered line inside any fence is not a step.

A heading that is itself `Step 3` keeps only `Step 3` as its label, so
`<sign> Step 3 and then prose` resolves to that heading and the prose does not
join the name (fixture `step-heading-prose-valid`). Whatever the name, put
punctuation right after it.

Known limits: a spelled-out number above ten is not recognised; a second
locator in one pointer (`step 3 and step 9`) is not read; and a lazily numbered
list (`1.` on every item) does not satisfy the check.
