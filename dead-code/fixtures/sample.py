"""Fixture for dead-code: a mix of truly-dead code and dynamically-reached code.

vulture flags all of these as unused — the point of this fixture is that the
LLM-triage pass must tell them apart, not that vulture already can.
"""
import os  # unused-import fixture case; not read by any of the code below
import pytest


def helper():
    """Never called from anywhere in this module or its (nonexistent) callers."""
    return 1


class UnusedHelper:
    """Never instantiated anywhere."""

    def run(self):
        return 2


def main():
    """Entrypoint — never called *within this file*, but it's what a console_scripts
    entry point or `python sample.py` would invoke. Reached dynamically, not dead."""
    return "entrypoint"


@pytest.fixture
def fixture_db():
    """pytest fixture — never called directly; pytest injects it by name via
    dependency injection, a mechanism vulture can't see."""
    return {"db": "connection"}
