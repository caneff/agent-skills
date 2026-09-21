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

`§ <Heading> step <n> ...` names the section `<Heading>`; `step <n>` and
whatever follows are locator and prose, not part of the name. The step number
is not checked against the target's numbered list. The keyword is `step` or
`Step`.

A reference whose name is itself "Step 3" is not this form. The name before
`step` must be non-empty, so the locator does not match; the whole text up to
the first punctuation is the name, and it needs a heading that starts with
"Step 3". Prose after it joins the name and the reference fails to resolve:
put punctuation right after the name.
