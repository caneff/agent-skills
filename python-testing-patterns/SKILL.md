---
name: python-testing-patterns
description: Python testing patterns and test-quality review using pytest. Use when writing, modifying, refactoring, or reviewing Python tests; before adding assertions, apply a critical-eye pass for behavior ownership, duplicate coverage, brittle string matching, overbroad fixture use, and unit-vs-integration boundaries.
---

# Python Testing Patterns

Comprehensive guide to implementing robust testing strategies in Python using pytest, fixtures, mocking, parameterization, and property-based testing.

## Test Quality Gate

Before adding or keeping a test, ask:

- What behavior does this test prove?
- Which module owns that behavior?
- Could this fail because an upstream or downstream layer changed?
- Is this exact string or object comparison testing public contract or incidental formatting?
- Does this duplicate another test at a higher or lower layer?
- Can this be a direct unit test instead of full workflow setup?
- Are shared fixtures hiding business examples that should be local to the test?
- Are we checking all fields because they matter, or because object comparison was easy?
- Would a helper reduce noise without hiding behavior?

Prefer:

- one test per owned behavior
- direct inputs to the target function
- small local builders for domain objects
- parametrization for the same behavior matrix
- exact text checks only where the formatter or composer owns wording

Delete or rewrite:

- tests that only prove a dependency or library default
- tests that repeat full workflow coverage in a unit file
- tests whose name says one behavior but assertions check unrelated fields
- tests that inspect private implementation unless no public behavior exposes the contract

## Core Concepts

**Test Discovery**: Files matching `test_*.py` or `*_test.py`, functions starting with `test_`

**Fixtures**: Reusable test resources with setup and teardown
- Scopes: `function` (default), `class`, `module`, `session`
- Composition: Build complex fixtures from simple ones
- Share via `conftest.py` for project-wide availability
- Keep expected-value-driving data local to the test; use shared fixtures for mechanics, builders, and cleanup, not hidden business examples.

**Assertions**: Use `assert` statements, `pytest.raises()` for exceptions

**Organization**: Separate `unit/`, `integration/`, `e2e/` directories

## Quick Reference

Load detailed references for specific topics:

| Task | Reference File |
|------|----------------|
| Pytest basics, test structure, AAA pattern | `~/.agents/skills/python-testing-patterns/references/pytest-fundamentals.md` |
| Fixtures, scopes, setup/teardown, conftest.py | `~/.agents/skills/python-testing-patterns/references/fixtures.md` |
| Parametrization, multiple test cases | `~/.agents/skills/python-testing-patterns/references/parametrized-tests.md` |
| Mocking, patching, unittest.mock, pytest-mock | `~/.agents/skills/python-testing-patterns/references/mocking.md` |
| Async tests, pytest-asyncio, event loops | `~/.agents/skills/python-testing-patterns/references/async-testing.md` |
| Property-based testing, Hypothesis, strategies | `~/.agents/skills/python-testing-patterns/references/property-based-testing.md` |
| Monkeypatch, environment variables, attributes | `~/.agents/skills/python-testing-patterns/references/monkeypatch.md` |
| Test structure, markers, conftest.py patterns | `~/.agents/skills/python-testing-patterns/references/test-organization.md` |
| Coverage measurement, reports, thresholds | `~/.agents/skills/python-testing-patterns/references/coverage.md` |
| Database, API, Redis, message queue testing | `~/.agents/skills/python-testing-patterns/references/integration-testing.md` |
| Best practices, test quality, fixture design | `~/.agents/skills/python-testing-patterns/references/best-practices.md` |

## Resources

- **pytest**: https://docs.pytest.org/
- **unittest.mock**: https://docs.python.org/3/library/unittest.mock.html
- **pytest-asyncio**: Testing async code
- **pytest-cov**: Coverage reporting
- **pytest-mock**: pytest wrapper for mock
- **Hypothesis**: https://hypothesis.readthedocs.io/
- **pytest-xdist**: Parallel test execution
- **testcontainers**: Docker containers for testing
