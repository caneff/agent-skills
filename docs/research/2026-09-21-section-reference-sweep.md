# Section-reference sweep for #955

Old regex (`§\s+(\d+|[A-Za-z][^§\n]{0,160})`) against new
(`(?<!\\)§\s+(\d+|[A-Za-z][^§`\n]*)`), over every tracked `*.md` outside
`docs/research/` and `tests/fixtures/`, at f92ad85.

- 90 references. 8 lines captured different trailing text (a code span or
  clause after the first punctuation mark).
- The resolved name of every reference (`reference_targets`) is identical
  under both. No reference stopped being checked; none newly fails.
- `python3 tests/check-section-references.py` exits 0 on the tree.
