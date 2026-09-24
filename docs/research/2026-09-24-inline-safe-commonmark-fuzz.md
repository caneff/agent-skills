# Fuzzing `burndown/sweep.py` `inline_safe` against CommonMark (#1109)

Question: after #1109, can a finding's title or text still put raw HTML or a
live `@mention` into a sweep ticket body?

## What was run

The oracle: a string leaks when its `inline_safe` output, rendered as
CommonMark, has `<i>` or an `@word` outside every `<code>` element. "Base" is
`sweep.py` at `20058c7`, the commit #1109 branched from; "final" is the
branch after its review round.

| Pass | Space | Parser | Base | Final |
|---|---|---|---|---|
| Exhaustive | every string of 1–8 tokens from `\`, `` ` ``, `a`, `<i>` (87,380) | markdown-it-py 3.0.0 `commonmark` | 58 leak | 0 |
| Random, seed 1109 | 200,000 strings of 1–14 tokens; tokens: `\` (×2), `` ` `` (×2), ` `` `, `a`, space, `<i>`, `@b`, `*`, `[` | markdown-it-py | 1,158 flagged | 0 flagged |
| Same 200k, flagged strings re-rendered | — | pandoc `-f commonmark` | 567 confirmed | 0 |
| Title and text pairs through `render_body`, seed 1109 | 20,000 pairs, each side 1–10 of the random pass's tokens | pandoc | 285 leak | 0 |

The exhaustive pass is exhaustive only over that four-token alphabet and
length. The random passes are samples, not bounds.

## markdown-it is not a sound oracle once `[` appears

Midway through the build, the scanner alone (before backticks outside a span
were escaped) had 716 strings flagged by markdown-it. Every one contained `[`,
and pandoc rendered all 716 with the code span intact. Example: the output
`` [`@b &lt;i>` *``&lt;i> `` renders in pandoc as
`[<code>@b &lt;i&gt;</code> *``&lt;i&gt;`. markdown-it prints the backticks
literally, with no code span. CommonMark gives code spans precedence over
link brackets, and `` [`a` `` alone renders correctly in markdown-it. So the
fault is in markdown-it's handling of a failed link label, not in the
scanner. Take a CommonMark verdict on bracketed text from pandoc
(commonmark-hs) or cmark, not from markdown-it alone.

## The ticket's second shape

The ticket gives `` a\``a`a<i>`` `` as the escaped-first-backtick shape. As
written it is safe at base: markdown-it and pandoc both render `&lt;i&gt;`.
The leaking shape is `` \``a`<i>` ``, with one trailing backtick. The
extra backtick most likely came from quoting the string inside backticks in
the review file. `sweep_test.py` pins the leaking shape, and keeps the
ticket's literal string as a regression case.

## A backtick could pair across fields

`inline_safe` made one field safe on its own, but `render_body` puts the title
and the text on one line. So an unmatched backtick in the title could close
on one in the text. With title ``a` `` and text `` b`<i>` ``, pandoc
rendered `a<code> — clump #901, #901, PR #950: b</code><i>`, with the `<i>`
live. Review finding C1 on #1109 raised it, and it was fixed in that round.
`inline_safe` now escapes every backtick it leaves outside a span, so the
backtick can pair with nothing. That is the pair row of the table above.

## Harness

The throwaway scripts loaded base with `git show 20058c7:burndown/sweep.py`
and final from the tree, and ran both through the oracle above. The pandoc
re-check joined every flagged output into one document as a separate
`x `-prefixed paragraph, so no line could start a list or link definition.
It then split pandoc's output on `<p>`. The pair pass rendered all 20,000
leftovers as one `render_body` document and split it on `<li>`.

One trap when mutation-testing this module: a `sed` mutation that keeps the
file's byte size (`==` → `>=`), restored by `cp` in the same second, leaves
a `__pycache__` entry Python still trusts. Clear `burndown/__pycache__`
after every mutate and restore.
