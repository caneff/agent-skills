# The exploration pass: what reaches Chris, and what is a line in a summary

The policy is `implement-spec/SKILL.md` § The exploration pass; the reader
is `implement-spec/contradictions.py`. This file is the evidence
behind them, and the shape of what the reader takes.

## Why the ticket list is read first

On #781's spec run the check flagged two decisions on
`sudokumaker-custom-constraints#366` as CONTRADICTED: `RULES_PREFIX`
hardcoded in `build_doc`, and no no-ring path in `framebuild.py`. Both
described exactly the gap that `#367` — a slice of that same spec, sitting in
the same ticket list — existed to close.

That is not drift. That is the spec correctly describing a future state, and
every spec with a prefactor slice generates it. The cost is not the noise
itself: it is that the noise arrives in the one channel that reaches Chris,
which is where a real contradiction has to be visible.

So the comparison is against the spec's own ticket list first, and only then
against Chris's attention.

## The three verdicts

| the code | a ticket of this spec builds it | verdict | reaches Chris |
| --- | --- | --- | --- |
| does it **differently** | either way | `contradicted` | yes |
| does not have it | yes | `not-yet-built` | no — a summary line naming that ticket |
| does not have it | no | `unbuilt` | no — a summary line, a gap in the slicing |
| does it as decided | — | `consistent` | no |

A `built_by` naming a ticket **outside** this spec is refused outright rather
than read either way: the whole defence is that *this spec* closes the gap
before it ships. Read as a defence it would excuse real drift; read as a
contradiction it would escalate a typo. Neither is an answer a reader may
pick on its own, so it fails closed and the pass says which decision it was.

An unknown `found` value fails closed for the same reason — a reader that
guesses at a spelling it does not know is a reader that can call a
contradiction "not yet built".

## What the reader takes

One JSON object: the spec's `tickets`, and its `decisions` — each with an
`id`, the `decision` as the spec states it, `found` (`absent`, `differs` or
`matches`), the `built_by` ticket or `null`, and the `evidence` the pass
read in the code.

```json
{
  "tickets": [366, 367, 368],
  "decisions": [
    {"id": "D1", "decision": "build_doc takes the rules prefix as an argument",
     "found": "absent", "built_by": 367,
     "evidence": "build_doc hardcodes RULES_PREFIX"}
  ]
}
```

Judging `found` and `built_by` is the pass's own work — reading code against
prose is not a parser's job. What the reader owns is what that judgment then
does: which verdict it earns, and whether it reaches Chris.
