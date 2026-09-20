#!/usr/bin/env bash
# The other direction: a healthy suite whose mutation check is *supposed* to go
# red, so it quotes the child checker's complaint and then passes. All three
# signature words appear here, every one of them mid-line, where a quoted
# failure lands. Only the column-0 anchor keeps this suite green.
#
# tests/section-references.test.sh is the real instance this stands in for.
echo "docs/agents/defect-classes.md:31: § Liveness says in not found in docs/agents/defect-classes.md"
echo "child checker printed FAIL and a Traceback, as this mutation requires"
echo "renamed heading rejected, as expected — the ERROR text above is the point"
echo "ok"
exit 0
