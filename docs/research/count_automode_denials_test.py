"""Tests for the auto-mode denial counter (#1538). Seams: transcript parsing
(denial kinds, the tool_use join, dedup across files, bad lines), edit-window
assignment, rates, and the soft_deny names read from settings. Plain test_*
functions under pytest, with `tmp_path` for the transcript trees."""
import json
import subprocess
import sys
from datetime import datetime, timezone

import count_automode_denials as c

CLASSIFIER = (
    "Permission for this action was denied by the Claude Code auto mode "
    "classifier. Reason: [{reason}]. If you have other tasks..."
)
HOOK = (
    "PreToolUse:Bash hook error: [/home/caneff/.claude/hooks/"
    "block-dangerous-git.sh]: BLOCKED: 'git reset --hard'"
)
REJECT = "The user doesn't want to proceed with this tool use."


TEST_EDITS = [
    c.Edit(datetime(2026, 10, 5, 12, tzinfo=timezone.utc), "first"),
    c.Edit(datetime(2026, 10, 8, 12, tzinfo=timezone.utc), "second"),
]


def ts(day, hour=12):
    return f"2026-10-{day:02d}T{hour:02d}:00:00.000Z"


def use(tid, when, name="Bash", **inp):
    return {"type": "assistant", "timestamp": when,
            "message": {"content": [
                {"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def result(tid, when, text, error=True, as_list=False):
    body = [{"type": "text", "text": text}] if as_list else text
    return {"type": "user", "timestamp": when,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                     "is_error": error, "content": body}]}}


def write(path, *lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(l if isinstance(l, str) else json.dumps(l)
                              for l in lines) + "\n")


def test_classifier_denial_carries_reason_and_joined_tool_input(tmp_path):
    write(tmp_path / "p" / "a.jsonl",
          use("t1", ts(3), command="git status --porcelain | wc -l"),
          result("t1", ts(3), CLASSIFIER.format(reason="Irreversible Local Destruction")))
    r = c.read_transcripts(tmp_path)
    [d] = r.denials
    assert (d.kind, d.reason, d.tool) == ("classifier", "Irreversible Local Destruction", "Bash")
    assert d.detail == "git status --porcelain | wc -l"
    assert len(r.calls) == 1


def test_list_shaped_result_content_is_read(tmp_path):
    write(tmp_path / "p" / "a.jsonl",
          use("t1", ts(3), command="x"),
          result("t1", ts(3), CLASSIFIER.format(reason="Production Deploy"), as_list=True))
    assert [d.reason for d in c.read_transcripts(tmp_path).denials] == ["Production Deploy"]


def test_hook_block_records_the_hook_script_name(tmp_path):
    write(tmp_path / "p" / "a.jsonl", use("t1", ts(3), command="git reset --hard"),
          result("t1", ts(3), HOOK))
    [d] = c.read_transcripts(tmp_path).denials
    assert (d.kind, d.reason) == ("hook", "block-dangerous-git.sh")


def test_a_classifier_outage_is_not_a_denial(tmp_path):
    text = ("The server-side auto mode classifier gave no verdict (timed out), "
            "so auto mode cannot determine the safety of Bash.")
    write(tmp_path / "p" / "a.jsonl", use("t1", ts(3), command="x"), result("t1", ts(3), text))
    [d] = c.read_transcripts(tmp_path).denials
    assert (d.kind, d.reason) == ("unavailable", "timed out")
    [w] = [w for w in c.tally(c.read_transcripts(tmp_path), TEST_EDITS) if w.label == "baseline"]
    assert (w.classifier, w.unavailable) == (0, 1)


def test_user_reject_is_its_own_kind(tmp_path):
    write(tmp_path / "p" / "a.jsonl", use("t1", ts(3), command="x"),
          result("t1", ts(3), REJECT))
    assert [d.kind for d in c.read_transcripts(tmp_path).denials] == ["reject"]


def test_classifier_denial_without_a_bracketed_reason_is_unlabelled(tmp_path):
    text = "denied by the Claude Code auto mode classifier. Reason: free text here."
    write(tmp_path / "p" / "a.jsonl", use("t1", ts(3), command="x"), result("t1", ts(3), text))
    [d] = c.read_transcripts(tmp_path).denials
    assert d.reason == c.UNLABELLED


def test_ordinary_tool_errors_are_not_denials(tmp_path):
    write(tmp_path / "p" / "a.jsonl", use("t1", ts(3), command="false"),
          result("t1", ts(3), "exit code 1"))
    r = c.read_transcripts(tmp_path)
    assert r.denials == [] and len(r.calls) == 1


def test_a_denial_whose_tool_use_is_missing_is_still_counted(tmp_path):
    write(tmp_path / "p" / "a.jsonl",
          result("gone", ts(3), CLASSIFIER.format(reason="Self-Modification")))
    [d] = c.read_transcripts(tmp_path).denials
    assert (d.tool, d.detail) == ("?", "")


def test_the_same_tool_use_in_two_files_counts_once(tmp_path):
    lines = [use("t1", ts(3), command="x"),
             result("t1", ts(3), CLASSIFIER.format(reason="Self-Modification"))]
    write(tmp_path / "p" / "a.jsonl", *lines)
    write(tmp_path / "p" / "b.jsonl", *lines)
    r = c.read_transcripts(tmp_path)
    assert len(r.calls) == 1 and len(r.denials) == 1
    assert r.duplicates == 2


def test_subagent_transcripts_are_read(tmp_path):
    write(tmp_path / "p" / "s" / "subagents" / "agent-x.jsonl", use("t1", ts(3), command="x"))
    assert len(c.read_transcripts(tmp_path).calls) == 1


def test_bad_lines_are_counted_not_skipped_silently(tmp_path):
    write(tmp_path / "p" / "a.jsonl", "{not json", use("t1", ts(3), command="x"))
    r = c.read_transcripts(tmp_path)
    assert r.bad_lines == 1 and len(r.calls) == 1


def test_a_line_with_no_timestamp_is_counted_as_undated(tmp_path):
    line = use("t1", ts(3), command="x")
    del line["timestamp"]
    write(tmp_path / "p" / "a.jsonl", line)
    r = c.read_transcripts(tmp_path)
    assert r.undated == 1 and r.calls == []


def test_coverage_reports_first_and_last_event(tmp_path):
    write(tmp_path / "p" / "a.jsonl", use("t1", ts(3), command="x"), use("t2", ts(9), command="y"))
    r = c.read_transcripts(tmp_path)
    assert (r.first.day, r.last.day) == (3, 9)


def test_windows_are_one_more_than_edits_and_labelled():
    ws = c.windows(TEST_EDITS)
    assert [w.label for w in ws] == ["baseline", "first", "second"]


def test_an_event_at_the_edit_instant_belongs_to_the_window_after_it():
    ws = c.windows(TEST_EDITS)
    at = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    just_before = datetime(2026, 10, 5, 11, 59, 59, tzinfo=timezone.utc)
    assert c.window_of(at, ws).label == "first"
    assert c.window_of(just_before, ws).label == "baseline"


def test_tally_buckets_calls_and_denials_per_window_and_rate(tmp_path):
    write(tmp_path / "p" / "a.jsonl",
          use("a", ts(4), command="1"), use("b", ts(4), command="2"),
          result("b", ts(4), CLASSIFIER.format(reason="Self-Modification")),
          use("c", ts(6), command="3"),
          result("c", ts(6), CLASSIFIER.format(reason="Self-Modification")),
          use("d", ts(9), command="4"))
    t = c.tally(c.read_transcripts(tmp_path), TEST_EDITS)
    rows = {w.label: w for w in t}
    assert (rows["baseline"].calls, rows["baseline"].classifier) == (2, 1)
    assert rows["baseline"].per_1k == 500.0
    assert (rows["first"].calls, rows["first"].classifier) == (1, 1)
    assert (rows["second"].calls, rows["second"].classifier) == (1, 0)
    assert rows["baseline"].reasons == {"Self-Modification": 1}


def test_a_window_with_no_calls_has_no_rate_not_a_zero(tmp_path):
    write(tmp_path / "p" / "a.jsonl", use("a", ts(4), command="1"))
    rows = {w.label: w for w in c.tally(c.read_transcripts(tmp_path), TEST_EDITS)}
    assert rows["second"].calls == 0 and rows["second"].per_1k is None


def test_soft_deny_names_are_the_text_before_the_named_marker(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"autoMode": {"soft_deny": [
        "Git Destructive [named+specifics — **must name:** the target]: A force-push",
        "Production Deploy [named+specifics — **must name:** x]: Deploying",
        "$defaults",
    ]}}))
    assert c.soft_deny_names(settings) == {"Git Destructive", "Production Deploy"}


def test_soft_deny_names_refuses_a_settings_file_with_no_soft_deny(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"autoMode": {}}))
    try:
        c.soft_deny_names(settings)
    except ValueError as e:
        assert "soft_deny" in str(e)
    else:
        raise AssertionError("an empty soft_deny must not read as 'no rules'")


def test_report_names_reasons_not_in_soft_deny_as_builtin(tmp_path):
    write(tmp_path / "p" / "a.jsonl", use("a", ts(9), command="x"),
          result("a", ts(9), CLASSIFIER.format(reason="Self-Modification")),
          use("b", ts(9), command="y"),
          result("b", ts(9), CLASSIFIER.format(reason="Production Deploy")))
    r = c.read_transcripts(tmp_path)
    out = c.render(r, c.tally(r, TEST_EDITS), {"Production Deploy"}, tz=timezone.utc)
    assert "| Production Deploy | soft_deny |" in out
    assert "| Self-Modification | built-in |" in out


def test_daily_table_counts_calls_and_denials_per_local_day(tmp_path):
    write(tmp_path / "p" / "a.jsonl",
          use("a", ts(4), command="1"), use("b", ts(4), command="2"),
          result("b", ts(4), CLASSIFIER.format(reason="Self-Modification")),
          use("c", ts(6), command="3"))
    r = c.read_transcripts(tmp_path)
    days = c.daily(r, tz=timezone.utc)
    assert days["2026-10-04"] == {"calls": 2, "classifier": 1, "hook": 0, "reject": 0, "unavailable": 0}
    assert days["2026-10-06"]["calls"] == 1


def test_unlabelled_reason_is_not_called_builtin(tmp_path):
    text = "denied by the Claude Code auto mode classifier. Reason: free text."
    write(tmp_path / "p" / "a.jsonl", use("a", ts(9), command="x"), result("a", ts(9), text))
    r = c.read_transcripts(tmp_path)
    out = c.render(r, c.tally(r, TEST_EDITS), set(), tz=timezone.utc)
    assert f"| {c.UNLABELLED} | — |" in out


def test_report_lists_days_inside_coverage_with_no_events(tmp_path):
    write(tmp_path / "p" / "a.jsonl", use("a", ts(3), command="1"), use("b", ts(6), command="2"))
    r = c.read_transcripts(tmp_path)
    assert c.missing_days(r, tz=timezone.utc) == ["2026-10-04", "2026-10-05"]
    out = c.render(r, c.tally(r, TEST_EDITS), set(), tz=timezone.utc)
    assert "No transcripts for: 10-04, 10-05" in out


def test_blocks_with_no_id_are_each_counted_not_merged(tmp_path):
    def bare(when):
        line = use("x", when, command="x")
        del line["message"]["content"][0]["id"]
        return line
    write(tmp_path / "p" / "a.jsonl", bare(ts(3)), bare(ts(4)))
    r = c.read_transcripts(tmp_path)
    assert len(r.calls) == 2 and r.duplicates == 0


def test_a_tmp_probe_hook_is_reported_apart_not_counted_as_a_block(tmp_path):
    text = ("PreToolUse:Bash hook error: [bash /tmp/claude-1000/probe/deny.sh]: "
            "probe: denied by a parallel hook")
    write(tmp_path / "p" / "a.jsonl", use("t1", ts(3), command="x"), result("t1", ts(3), text))
    r = c.read_transcripts(tmp_path)
    assert r.denials == [] and r.probe_hooks == 1


def test_soft_deny_rule_without_the_named_marker_is_refused(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"autoMode": {"soft_deny": [
        "$defaults", "Production Deploy: Deploying to production"]}}))
    try:
        c.soft_deny_names(settings)
    except ValueError as e:
        assert "[named" in str(e)
    else:
        raise AssertionError("a rule with no marker must not read as built-in")


SETTINGS = {"autoMode": {"soft_deny": [
    "Production Deploy [named+specifics — **must name:** x]: Deploying"]}}


def run_main(tmp_path, *args, settings=SETTINGS):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings))
    return subprocess.run(
        [sys.executable, str(__import__("pathlib").Path(c.__file__)), "--settings", str(path), *args],
        capture_output=True, text=True)


def test_main_marks_soft_deny_reasons_from_the_settings_file(tmp_path):
    root = tmp_path / "t"
    write(root / "p" / "a.jsonl", use("a", ts(9), command="x"),
          result("a", ts(9), CLASSIFIER.format(reason="Production Deploy")))
    r = run_main(tmp_path, "--root", str(root))
    assert r.returncode == 0, r.stderr
    assert "| Production Deploy | soft_deny |" in r.stdout


def test_main_json_carries_coverage(tmp_path):
    root = tmp_path / "t"
    write(root / "p" / "a.jsonl", "{bad", use("a", ts(9), command="x"))
    r = run_main(tmp_path, "--root", str(root), "--json")
    out = json.loads(r.stdout)
    assert out["coverage"]["bad_lines"] == 1 and out["coverage"]["calls"] == 1


def test_main_refuses_a_missing_transcript_root(tmp_path):
    r = run_main(tmp_path, "--root", str(tmp_path / "nope"), "--json")
    assert r.returncode == 2 and "not a directory" in r.stderr


def test_main_refuses_a_root_with_no_tool_calls(tmp_path):
    (tmp_path / "t").mkdir()
    r = run_main(tmp_path, "--root", str(tmp_path / "t"))
    assert r.returncode == 2 and "no tool calls" in r.stderr


def test_main_validates_settings_in_json_mode_too(tmp_path):
    root = tmp_path / "t"
    write(root / "p" / "a.jsonl", use("a", ts(9), command="x"))
    r = run_main(tmp_path, "--root", str(root), "--json", settings={"autoMode": {}})
    assert r.returncode == 2 and "soft_deny" in r.stderr
