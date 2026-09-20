#!/usr/bin/env python3
"""Tests for the exploration pass's contradiction check (#897).

One seam, named on the ticket: `check(decisions, tickets)` over a fixture
spec holding a decision a ticket of that spec builds, a decision the code
implements differently, and a decision the code does not mention. What each
of the three does — escalate to Chris, or land as a summary line — is what
these assert.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contradictions as C  # noqa: E402

CHECKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "contradictions.py")

# The fixture spec: #366 is the slice under exploration, #367 the prefactor
# that builds what #366's decision assumes, #368 an unrelated slice. Shaped
# after the run the rule came from — #781's spec run on
# sudokumaker-custom-constraints#366.
TICKETS = [366, 367, 368]

BUILT_BY_A_SLICE = {
    "id": "D1",
    "decision": "build_doc takes the rules prefix as an argument",
    "found": "absent",
    "built_by": 367,
    "evidence": "build_doc hardcodes RULES_PREFIX — a caller-supplied prefix is absent, not done another way",
}


def test_a_decision_a_ticket_in_this_spec_builds_does_not_escalate():
    got = C.check([BUILT_BY_A_SLICE], TICKETS)
    assert [r.verdict for r in got] == ["not-yet-built"], got
    assert [r.escalates for r in got] == [False], got


IMPLEMENTED_DIFFERENTLY = {
    "id": "D2",
    "decision": "the no-ring path renders a bare header",
    "found": "differs",
    "built_by": None,
    "evidence": "framebuild.py renders the ring header with an empty ring",
}


def test_a_decision_the_code_implements_differently_escalates():
    got = C.check([IMPLEMENTED_DIFFERENTLY], TICKETS)
    assert [r.verdict for r in got] == ["contradicted"], got
    assert [r.escalates for r in got] == [True], got


NOT_IN_THE_CODE = {
    "id": "D3",
    "decision": "the solver reports a ring-free grid as unsatisfiable",
    "found": "absent",
    "built_by": None,
    "evidence": "nothing in the tree mentions it",
}


def test_a_decision_the_code_does_not_mention_does_not_escalate():
    # The third of the ticket's three: absent, and no slice of this spec
    # builds it. A slicing gap, not drift — it belongs in the summary, and
    # only "the code does this, differently" reaches Chris.
    got = C.check([NOT_IN_THE_CODE], TICKETS)
    assert [r.verdict for r in got] == ["unbuilt"], got
    assert [r.escalates for r in got] == [False], got


def test_exactly_one_of_the_three_escalates():
    got = C.check([BUILT_BY_A_SLICE, IMPLEMENTED_DIFFERENTLY, NOT_IN_THE_CODE],
                  TICKETS)
    assert [r.id for r in got if r.escalates] == ["D2"], got


def test_not_yet_built_is_a_summary_line_naming_the_ticket_that_builds_it():
    line = C.check([BUILT_BY_A_SLICE], TICKETS)[0].line
    assert "not yet built" in line, line
    assert "#367" in line, line
    assert "CONTRADICTED" not in line, line


def test_the_summary_counts_what_the_controller_must_carry_to_chris():
    out = C.render(C.check([BUILT_BY_A_SLICE, IMPLEMENTED_DIFFERENTLY,
                            NOT_IN_THE_CODE], TICKETS))
    assert out.endswith("3 decisions checked, 1 contradiction for Chris"), out
    # Escalations last: the summary's other lines precede the one that is a
    # ruling to make.
    assert out.splitlines()[-2].startswith("D2 CONTRADICTED"), out


def test_a_decision_built_by_a_ticket_outside_this_spec_is_an_error():
    # The defence is "a ticket of *this spec* closes the gap before it ships".
    # A number from somewhere else is not that, and guessing which way to read
    # it either excuses real drift or escalates noise — so it is neither
    # verdict, it is an error against that decision.
    stranger = {**BUILT_BY_A_SLICE, "built_by": 999}
    got = C.check([stranger], TICKETS)
    assert [r.verdict for r in got] == ["error"], got
    assert [r.escalates for r in got] == [False], got
    assert "#999" in got[0].line and "not a ticket of this spec" in got[0].line, got


def test_an_unknown_found_value_is_an_error():
    got = C.check([{**BUILT_BY_A_SLICE, "found": "CONTRADICTED"}], TICKETS)
    assert [r.verdict for r in got] == ["error"], got
    assert "found is" in got[0].line, got


def test_one_malformed_decision_does_not_hide_a_real_contradiction():
    # The check's whole job is to surface a contradiction. Raising on the
    # first bad `built_by` emitted nothing for anything, so one stale entry
    # blinded the pass to every `differs` behind it.
    stranger = {**BUILT_BY_A_SLICE, "built_by": 999}
    got = C.check([stranger, IMPLEMENTED_DIFFERENTLY, NOT_IN_THE_CODE], TICKETS)
    assert [r.verdict for r in got] == ["error", "contradicted", "unbuilt"], got
    assert [r.id for r in got if r.escalates] == ["D2"], got


def test_the_summary_counts_the_errors_beside_the_contradictions():
    stranger = {**BUILT_BY_A_SLICE, "built_by": 999}
    out = C.render(C.check([stranger, IMPLEMENTED_DIFFERENTLY], TICKETS))
    assert "1 exploration error" in out, out
    assert "1 contradiction for Chris" in out, out


def test_the_cli_reads_an_exploration_file_and_prints_the_summary():
    import json
    import subprocess
    import tempfile
    payload = {"tickets": TICKETS,
               "decisions": [BUILT_BY_A_SLICE, IMPLEMENTED_DIFFERENTLY,
                             NOT_IN_THE_CODE]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        path = fh.name
    try:
        out = subprocess.run([sys.executable, CHECKER, path],
                             capture_output=True, text=True)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert "1 contradiction for Chris" in out.stdout, out.stdout


def test_the_cli_fails_loud_on_a_malformed_exploration_file():
    import json
    import subprocess
    import tempfile
    payload = {"tickets": TICKETS,
               "decisions": [{"id": "D9"}, IMPLEMENTED_DIFFERENTLY]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        path = fh.name
    try:
        out = subprocess.run([sys.executable, CHECKER, path],
                             capture_output=True, text=True)
    finally:
        os.unlink(path)
    assert out.returncode == 1, out.stdout
    assert "is missing" in out.stderr and "D9" in out.stderr, out.stderr


def test_a_ticket_list_entry_that_is_not_a_number_is_refused():
    # The list is what the whole defence is checked against; a malformed
    # entry silently dropped would turn a "not yet built" into a
    # contradiction on Chris's desk.
    try:
        C.check([BUILT_BY_A_SLICE], [366, "three-six-seven", 368])
    except C.SpecError as exc:
        assert "not a ticket number" in str(exc), exc
    else:
        raise AssertionError("a malformed ticket list was accepted")


def test_the_fixture_evidence_states_which_side_of_the_boundary_it_is_on():
    # C1: `absent` and `differs` are the whole rule, so the evidence a pass
    # records has to say which it saw — "the code hardcodes it" reads as
    # both until the decision's own behaviour is named.
    assert "absent" in BUILT_BY_A_SLICE["evidence"], BUILT_BY_A_SLICE


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
