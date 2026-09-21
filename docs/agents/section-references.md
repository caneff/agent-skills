# Section references

A cross-reference to a heading in Markdown prose is written `§ <Heading>`.
`tests/check-section-references.py` checks every tracked Markdown file except
`docs/research/` and `tests/fixtures/`, and fails the suite on a reference that
does not resolve.

## Which file a reference points at

- A `.md` path on the same line names the target; the last one that resolves
  wins. Paths resolve against the source file's directory, then the repo root;
  `~/.agents/skills/` maps to the repo root.
- "this file" on the line targets the file the line is in.
- "of that file" after the `§` targets the last file named on an earlier line.
- With no path on the line, the reference targets its own file. If the
  previous line named another file, a bare `§` is a collision and fails:
  name the file on the same line.

## The name

- The name runs from `§` to the first of `. , ; : ! ? ) } ]`, a `'s`, or
  ` and §`; a trailing ` and` is dropped. Write the heading, then punctuation.
- A heading only has to start with the name, so a reference reading "The merge" matches a
  heading "The merge: who and when". Use enough words to be unambiguous.
- A bare number after the section sign matches a heading that starts with that
  number and a period.

## The step locator

`§ <Heading> step <n> ...` names the section `<Heading>`; `step <n>` and
whatever follows are locator and prose, not part of the name. The step number
is not checked against the target's numbered list.

A reference whose name is itself "Step 3" is not this form. The name before
`step` must be non-empty, so it is read as a whole name and needs a heading
that starts with "Step 3". A reference to such a heading that carries prose
after it is over-read as a locator: put punctuation right after the name.
