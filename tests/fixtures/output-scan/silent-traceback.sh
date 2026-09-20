#!/usr/bin/env bash
# Witnesses the `Traceback` third of the set: a suite whose helper died, whose
# stderr was folded into the captured output, and which still exited 0.
#
# One fixture per signature word, because the gate greps with `-m1`: a single
# fixture printing all three would keep matching on the first, and deleting
# either of the other two from the set would go unnoticed.
echo "Traceback (most recent call last):"
echo "  File \"build.py\", line 12, in <module>"
echo "KeyError: 'version'"
exit 0
