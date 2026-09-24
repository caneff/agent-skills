# Fuzzing `burndown/sweep.py` `inline_safe` against CommonMark (#1109)

Question: after #1109's scanner, can a finding's text still put raw HTML or a
live `@mention` into a sweep ticket body?

## What was run

The oracle: a string leaks when its `inline_safe` output, rendered as
CommonMark, has `<i>` or an `@word` outside every `<code>` element.

| Pass | Space | Parser | Old regex (`a93ef14`) | New scanner |
|---|---|---|---|---|
| Exhaustive | every string of 1–8 tokens from `\`, `` ` ``, `a`, `<i>` (87,380) | markdown-it-py 3.0.0 `commonmark` | 58 leak | 0 |
| Random, seed 1109 | 200,000 strings of 1–14 tokens from `\ \ `` ` ` `` `` a`, space, `<i>`, `@b`, `*`, `[` | markdown-it-py | 1,158 flagged | 716 flagged |
| Same 200k, flagged strings re-rendered | — | pandoc `-f commonmark` | 567 confirmed | **0 confirmed** |

The exhaustive pass is exhaustive only over that four-token alphabet and
length. The random pass is a sample, not a bound.

## markdown-it is not a sound oracle once `[` appears

Every new-scanner string that markdown-it flagged contains `[`, and pandoc
renders all 716 with the code span intact. Example: `` [`@b <i>` *``<i> ``
becomes `` [`@b &lt;i>` *``&lt;i> ``. pandoc renders it as
`[<code>@b &lt;i&gt;</code> *``&lt;i&gt;`. markdown-it prints the backticks
literally, with no code span. CommonMark gives code spans precedence over
link brackets, and `` [`a` `` alone renders correctly in markdown-it. So the
fault is in markdown-it's handling of a failed link label, not in the
scanner. Take a CommonMark verdict on bracketed text from pandoc
(commonmark-hs) or cmark, not from markdown-it alone.

## The ticket's second shape

The ticket gives `` a\``a`a<i>`` `` as the escaped-first-backtick shape. As
written it is safe under the old regex: markdown-it and pandoc both render
`&lt;i&gt;`. The leaking shape is `` \``a`<i>` ``, with one trailing backtick,
and that is the one `sweep_test.py` pins. The extra backtick most likely
came from quoting the string inside backticks in the review file.

## Still open: a backtick can pair across fields

`inline_safe` makes one field safe on its own. `render_body` puts the title
and the text on one line, so an unmatched backtick in the title can close on
one in the text. With title ``a` `` and text `` b`<i>` ``, pandoc renders
`a<code> — clump #901, #901, PR #950: b</code><i>`` — live `<i>`. #1109's
worker reported it as a follow-up rather than fixing it there, since the
ticket asked for escape and run-length handling inside one string.

## Harness

The throwaway scripts loaded the old module from `git show a93ef14:burndown/sweep.py`
and the new one from the tree, and ran both through the oracle above. The
pandoc re-check joined every flagged output into one document as a separate
`x `-prefixed paragraph, so no line could start a list or link definition.
It then split pandoc's output on `<p>`.

One trap when mutation-testing this module: a `sed` mutation that keeps the
file's byte size (`==` → `>=`), restored by `cp` in the same second, leaves
a `__pycache__` entry Python still trusts. Clear `burndown/__pycache__`
after every mutate and restore.
