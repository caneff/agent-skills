# Root standards fixture (dev-home only)

This file exists so `.sandcastle/tests/review-standards-loading.test.mjs` has a
root `CODING_STANDARDS.md` to detect, mirroring the real target repo (where
`setup-python-repo` produces one). It is NOT installed into targets — the skill
copies only `templates/.sandcastle/`. Its first line is the test's marker.
