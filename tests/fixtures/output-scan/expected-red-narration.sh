#!/usr/bin/env bash
# The other direction: a healthy suite whose mutation check is *supposed* to go
# red, so it narrates the child checker's complaint and then passes. Every
# failure word the scan hunts appears here, mid-line, where the child printed
# it. This suite must stay green — see tests/section-references.test.sh, the
# real instance this fixture stands in for.
echo "docs/agents/defect-classes.md:31: § Liveness says in not found in docs/agents/defect-classes.md"
echo "checker rejected the renamed heading, as expected — ERROR text above is the point"
echo "ok"
exit 0
