"""`implement-spec/SKILL.md` names a durable home for the candidates and
in-flight files (#1896): two runs kept them under /tmp, lost them to a reboot
and rebuilt them by hand. The home is a per-run directory, because a run id
may contain dots and `<run-id>.candidates.json` could be another run's file."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "SKILL.md")


def step_2():
    with open(SKILL) as f:
        text = f.read()
    match = re.search(r"^2\. Read the frontier.*?(?=^3\. )", text, re.S | re.M)
    assert match, "step 2 not found in implement-spec/SKILL.md"
    return match.group(0)


def test_step_2_names_candidates_path_under_spec_run_cache():
    assert "~/.cache/spec-run/<run-id>/candidates.json" in step_2()


def test_step_2_names_in_flight_path_under_spec_run_cache():
    assert "~/.cache/spec-run/<run-id>/in-flight.json" in step_2()
