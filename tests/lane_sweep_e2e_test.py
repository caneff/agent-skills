"""End-to-end test for spec #1734: the lane machinery's removals, bug fixes,
vocabulary and restructures from the 2026-11-13 sweep.

Each criterion is driven through the entry point a controller, a worker or
drain reaches, not through a private helper:

- `loop.py box` and `loop.py dispatch` refuse `--add-gb`, and `loop.py` has
  no `announce`, `resolve_via_binary`, `admit` or `refill` left (#1761);
- `loop.py` dispatches each subcommand through its own handler, and the
  agent counting it used to hold lives in `agents.py`, with `loop.py` under
  1000 lines (#1769, #1770);
- one heading rule: a heading indented up to three spaces is a heading and
  one indented four is not, read the same way by `frontier`'s blocker reader
  and by `closing_ticket.py`'s seam reader (#1772);
- drain's model-facing prompts call a drain pass a drain (#1766), and a hung
  `herdr` stops drain's worker probe with an error naming herdr (#1763);
- `codex-usage-gate.py --percent` keeps `unknown` on stdout and names the
  cause on stderr (#1763).

What a green run does NOT cover (the seam is blind to it):
- the Rust lane's halves of the spec: `merge-cleanup` stopping on a failed
  `git worktree list` (#1762), `worktree::list` as the one listing (#1767),
  and the merged runner and issue_state reads (#1768). Those are driven by
  `flow/lane/tests/*.rs` under the same `bash tests/all.sh`, not here;
- the worker alert hooks' shared delivery step (#1773), driven by
  `flow/claude/hooks/worker-*-alert.test.sh`;
- whether a controller, a worker or a reviewer follows the rewritten prose in
  `implement-spec/SKILL.md`, `implement/SKILL.md`,
  `multi-axis-code-review/SKILL.md` and `flow/claude/agents/diff-reviewer.md`
  (#1761, #1764): that is read by opening the files, not asserted.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "implement-spec"
LOOP = SPEC / "loop.py"
CLOSING = SPEC / "closing_ticket.py"
DRAIN = ROOT / "drain" / "drain.py"
GATE = ROOT / "implement" / "codex-usage-gate.py"

sys.path.insert(0, str(SPEC))
import frontier  # noqa: E402
import loop  # noqa: E402


def run(*argv, env=None, cwd=None):
    return subprocess.run([sys.executable, *map(str, argv)], capture_output=True,
                          text=True, env=env, cwd=cwd)


def test_loop_refuses_add_gb_on_box_and_dispatch(tmp_path):
    box = run(LOOP, "box", "--processes", "1", "--committed-gb", "0", "--live", "0",
              "--add-gb", "1")
    assert box.returncode == 2 and "unrecognized arguments: --add-gb" in box.stderr, box
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    dispatch = run(LOOP, "dispatch", "--candidates", empty, "--in-flight", empty,
                   "--run", "run-1", "--free", "1", "--committed-gb", "0",
                   "--add-gb", "1")
    assert dispatch.returncode == 2 and "unrecognized arguments: --add-gb" in dispatch.stderr, dispatch


def test_loop_keeps_no_removed_function_and_no_agent_counting():
    for gone in ("announce", "resolve_via_binary", "admit", "refill"):
        assert not hasattr(loop, gone), gone
    assert len(LOOP.read_text().splitlines()) < 1000
    import agents
    for moved in ("box_check", "_proc_start", "count_agent_processes",
                  "count_working_herdr_agents"):
        assert hasattr(agents, moved) and not hasattr(loop, moved), moved


def test_loop_dispatches_a_subcommand_through_its_handler(tmp_path):
    candidates = tmp_path / "candidates.json"
    candidates.write_text('[{"tickets": [5], "files": ["a.py"], "closure": ["a.py"]},'
                          ' {"tickets": [6], "files": ["a.py"], "closure": ["a.py"]}]')
    hub = run(LOOP, "hub", "--candidates", candidates, "--landed", "a.py")
    assert hub.returncode == 0 and "re-explore" in hub.stdout, hub


def test_one_heading_rule_for_blockers_and_the_seam(tmp_path):
    # " \t" is the case that tells the rules apart: `visible()` keeps the line
    # (it drops only four spaces or a leading tab), CommonMark reads it as code,
    # and the old `[ \t]*` rule read it as a heading.
    for indent, is_heading in (("", True), ("   ", True), ("    ", False),
                               (" \t", False)):
        body = f"{indent}## Blocked by\n\n- #12\n"
        stated = frontier.blocked_by_section(body)
        assert (frontier.section_blockers(stated)[0] == [12]) is is_heading, (indent, stated)

        repo = tmp_path / f"indent{indent!r}".replace("'", "")
        repo.mkdir()
        (repo / "AGENTS.md").write_text(
            f"# R\n\n{indent}## End-to-end seam\n\n- **Seam**: `bash t.sh`\n"
            "- **Blind to**: the live app\n")
        closing = run(CLOSING, repo, 7, "--no-surface", "--default", "main")
        assert (closing.returncode == 0) is is_heading, (indent, closing)
        if is_heading:
            assert "`bash t.sh`" in closing.stdout, closing.stdout


def drain_python(code, tmp_path, **env):
    full = {**os.environ, **env}
    return run("-c", f"import importlib.util as u\n"
               f"s = u.spec_from_file_location('drain_e2e', {str(DRAIN)!r})\n"
               f"d = u.module_from_spec(s); s.loader.exec_module(d)\n{code}",
               env=full, cwd=tmp_path)


def test_drain_prompts_say_drain(tmp_path):
    p = drain_python("print(d.chooser_prompt(5, [], 3)); print('---');"
                     " print(d.nudge_text('stuck', False, 'build'))", tmp_path)
    assert p.returncode == 0, p.stderr
    chooser, nudge = p.stdout.split("---\n")
    assert chooser.startswith("Bundle choice for an unattended drain."), chooser
    assert nudge.startswith("Unattended drain, no controller"), nudge
    assert "unattended run" not in p.stdout.lower(), p.stdout


def test_a_hung_herdr_stops_drains_probe_naming_herdr(tmp_path):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    herdr = fakebin / "herdr"
    herdr.write_text("#!/bin/sh\nexec sleep 30\n")
    herdr.chmod(0o755)
    p = drain_python("try:\n    d.agent_info('skills-9')\nexcept d.DrainStop as e:\n"
                     "    print('stopped:', e)\n", tmp_path,
                     PATH=f"{fakebin}:{os.environ['PATH']}", DRAIN_HERDR_SECONDS="0.5")
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("stopped: herdr agent get skills-9: timed out"), p.stdout


def test_codex_gate_percent_names_its_cause(tmp_path):
    # A copy of the gate with no helper beside it: loading the helper raises.
    (tmp_path / "implement").mkdir()
    gate = tmp_path / "implement" / "codex-usage-gate.py"
    gate.write_text(GATE.read_text())
    p = run(gate, "--percent", env={"CODEX_HOME": str(tmp_path), "HOME": str(tmp_path),
                                    "PATH": "/nonexistent"})
    assert (p.returncode, p.stdout) == (30, "unknown\n"), p
    assert "codex usage unknown: FileNotFoundError:" in p.stderr, p.stderr
