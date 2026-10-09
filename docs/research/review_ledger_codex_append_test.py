"""Tests for the Codex rows the controller writes at merge (#1269): `append --type codex-<phase>`
and `harvest`, both reading the usage change from the two live readings the pass's record carries
(`usage_before`, `usage_after`, as `codex-usage-gate.py --percent` prints them). Every test runs the
command line; HOME is a temp dir, so no default path reaches the real ~/.cache."""
import json

import pytest

from review_ledger_support import OUT_CLEAN, OUT_REFUSED, OUT_TWO, Env, put

STARTED, COMPLETED = "2026-09-30T09:00:00-04:00", "2026-09-30T09:02:30-04:00"
W1, W2 = 1790000000, 1790600000  # two windows' reset times


class Passes(Env):
    """The Codex cache and ledger of one test, and the commands that write them."""

    def __init__(self, tmp):
        super().__init__(tmp)
        self.cache = tmp / "cache"
        self.skills = self.cache / "skills"

    def record(self, ticket, phase="gate", before=None, after=None, out=OUT_CLEAN, status=0):
        """A pass's record and `.out`; `before` and `after` are the readings the controller took
        (a string, or None for a record that carries none)."""
        put(self.skills, ticket, phase, STARTED, COMPLETED, out, status)
        path = self.skills / f"codex-adversarial-{ticket}-{phase}.json"
        rec = json.loads(path.read_text())
        for key, value in (("usage_before", before), ("usage_after", after)):
            if value is not None:
                rec[key] = value
        path.write_text(json.dumps(rec) + "\n")

    def append(self, ticket, phase, *extra):
        return self.run("append", "--repo", "skills", "--ticket", ticket, "--type", f"codex-{phase}",
                        "--cache", self.cache, "--ledger", self.ledger, *extra)

    def ok(self, *a):
        r = self.append(*a)
        assert r.returncode == 0, r.stderr
        return r

    def only_row(self):
        (row,) = self.rows().values()
        return row

    def harvest(self):
        r = self.run("harvest", "--cache", self.cache, "--transcripts", self.tmp, "--ledger", self.ledger,
                     "--review-file", self.tmp / "h.md")
        assert r.returncode == 0, r.stderr


@pytest.fixture
def px(tmp_path):
    return Passes(tmp_path)


class TestUsageChange:
    def test_a_pass_records_the_usage_change_between_its_two_readings(self, px):
        px.record(500, before=f"10 {W1}", after=f"12.5 {W1}", out=OUT_TWO)
        px.ok(500, "gate")
        row = px.only_row()
        assert row["type"] == "codex-gate"
        assert row["cost"]["usage_delta"] == {"status": "known", "before": 10.0, "after": 12.5, "delta": 2.5}
        assert row["cost"]["wall_clock"]["seconds"] == 150
        assert [f["severity"] for f in row["findings"]] == ["high", "medium"]

    def test_a_pass_that_used_nothing_is_a_known_zero(self, px):
        px.record(500, before=f"10 {W1}", after=f"10 {W1}")
        px.ok(500, "gate")
        assert px.only_row()["cost"]["usage_delta"]["delta"] == 0

    def test_each_phase_writes_its_own_row(self, px):
        for phase in ("gate", "second"):
            px.record(500, phase, f"1 {W1}", f"2 {W1}")
            px.ok(500, phase)
        assert sorted(r["type"] for r in px.rows().values()) == ["codex-gate", "codex-second"]

    @pytest.mark.parametrize("extra", [(), ("--skip-reason", "usage capped"), ("--refusal", "stale")])
    def test_the_retired_third_phase_is_refused_by_name(self, px, extra):
        """#1360: the second pass is final, so a stale controller's third row is refused, not written."""
        px.record(500, "third", f"1 {W1}", f"2 {W1}")
        r = px.append(500, "third", *extra)
        assert r.returncode != 0, extra
        assert "codex-third is retired" in r.stderr
        assert "append no row for it" in r.stderr
        assert not px.ledger.exists()

    def test_a_missing_or_unreadable_reading_is_unknown_never_zero(self, px):
        good = f"10 {W1}"
        cases = [(None, good), (good, None), (None, None), ("unknown", good), (good, "unknown"), ("", good),
                 ("abc", good), ("nan 5", good), (f"-3 {W1}", good), ("10", good), (f"10 {W1} x", good),
                 (good, f"inf {W1}"), (f"10 nan", good)]
        for n, (before, after) in enumerate(cases):
            px.record(510 + n, before=before, after=after)
            px.ok(510 + n, "gate")
        assert len(px.rows()) == len(cases)
        for row in px.rows().values():
            delta = row["cost"]["usage_delta"]
            assert delta["status"] == "unknown", row["row_id"]
            assert "delta" not in delta

    def test_readings_of_different_windows_are_never_subtracted(self, px):
        # The primary window was the worst before the pass and the secondary after: 22 -> 23 is not a 1-point cost,
        # and neither is 20 -> 25 across two windows.
        px.record(500, before=f"20 {W1}", after=f"25 {W2}")
        px.ok(500, "gate")
        delta = px.only_row()["cost"]["usage_delta"]
        assert delta["status"] == "unknown"
        assert "different windows" in delta["reason"]

    def test_a_percent_that_fell_within_one_window_is_unknown(self, px):
        px.record(500, before=f"90 {W1}", after=f"3 {W1}")
        px.ok(500, "gate")
        delta = px.only_row()["cost"]["usage_delta"]
        assert delta["status"] == "unknown"
        assert "fell" in delta["reason"]

    def test_a_refused_run_keeps_its_usage_change_and_is_not_a_clean_pass(self, px):
        px.record(500, before=f"99 {W1}", after=f"100 {W1}", out=OUT_REFUSED, status=1)
        px.ok(500, "gate")
        row = px.only_row()
        assert row["status"]["fields"]["findings"]["status"] == "refused"
        assert row["cost"]["usage_delta"]["delta"] == 1.0

    def test_no_record_for_the_phase_is_refused_and_writes_nothing(self, px):
        px.record(500)
        r = px.append(500, "second")
        assert r.returncode == 2
        assert "expected exactly one" in r.stderr
        assert not px.ledger.exists()

    def test_appending_the_same_pass_twice_leaves_one_row(self, px):
        px.record(500, before=f"1 {W1}", after=f"2 {W1}")
        px.ok(500, "gate")
        px.ok(500, "gate")
        assert len(px.rows()) == 1

    def test_a_later_harvest_writes_the_same_row(self, px):
        px.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        px.ok(500, "gate")
        appended = px.only_row()
        px.harvest()
        assert px.only_row() == appended

    def test_a_harvest_after_the_record_is_pruned_keeps_the_appended_row(self, px):
        # #1304: append, harvest, the 14-day prune takes the record, harvest again.
        px.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        px.record(501)  # a second record, so the cache is not empty once ticket 500's is gone
        px.ok(500, "gate")
        appended = px.rows()["skills/500/codex-gate/1/codex-adversarial-500-gate"]
        px.harvest()
        for suffix in (".json", ".out"):
            (px.skills / f"codex-adversarial-500-gate{suffix}").unlink()
        px.harvest()
        assert px.rows().get("skills/500/codex-gate/1/codex-adversarial-500-gate") == appended

    def test_a_harvest_after_the_out_is_pruned_keeps_the_known_findings(self, px):
        # The controller writes the .out seconds before the .json, so the prune can take it first.
        px.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        px.ok(500, "gate")
        appended = px.only_row()
        (px.skills / "codex-adversarial-500-gate.out").unlink()
        px.harvest()
        row = px.only_row()
        assert (row["findings"], row["status"]["fields"]["findings"]) == \
            (appended["findings"], appended["status"]["fields"]["findings"])

    def test_other_rows_of_the_ticket_are_not_written(self, px):
        px.record(500, "gate")
        px.record(500, "second")
        px.ok(500, "gate")
        assert [r["type"] for r in px.rows().values()] == ["codex-gate"]


class TestSkippedPass:
    def test_a_skipped_pass_writes_a_row_with_its_reason_and_zero_cost(self, px):
        reason = "codex usage 100% - capped, resets 2026-10-03 09:00"
        r = px.run("append", "--repo", "skills", "--ticket", 500, "--type", "codex-gate", "--skip-reason", reason,
                   "--ledger", px.ledger)
        assert r.returncode == 0, r.stderr
        row = px.only_row()
        assert row["type"] == "codex-gate"
        assert row["skip_reason"] == reason
        assert row["cost"]["wall_clock"] == {"status": "known", "seconds": 0}
        assert row["cost"]["usage_delta"]["delta"] == 0
        assert row["findings"] == []
        assert row["status"]["fields"]["findings"] == {"status": "skipped", "reason": reason}

    def test_a_skipped_pass_is_not_a_clean_pass_in_the_report(self, px):
        px.run("append", "--repo", "skills", "--ticket", 500, "--type", "codex-gate", "--skip-reason", "capped",
               "--ledger", px.ledger)
        px.record(501, before=f"1 {W1}", after=f"2 {W1}")
        px.ok(501, "gate")
        r = px.run("report", "--ledger", px.ledger, "--format", "json")
        assert r.returncode == 0, r.stderr
        (t,) = [t for t in json.loads(r.stdout)["types"] if t["type"] == "codex-gate"]
        assert (t["rows"], t["clean_rows"], t["skipped_rows"], t["unknown_finding_rows"]) == (2, 1, 1, 0)
        assert (t["usage_percent"], t["unknown_usage_rows"]) == (1.0, 0)

    @pytest.mark.parametrize("extra", [["--skip-reason", "  "], ["--skip-reason", "x", "--cache", "CACHE"],
                                       ["--skip-reason", "x", "--refusal", "y"],
                                       ["--skip-reason", "x", "--round", "2"]])
    def test_an_empty_reason_or_a_cache_beside_it_is_refused(self, px, extra):
        extra = [str(px.cache) if a == "CACHE" else a for a in extra]
        r = px.run("append", "--repo", "skills", "--ticket", 500, "--type", "codex-gate", *extra,
                   "--ledger", px.ledger)
        assert r.returncode == 2, extra
        assert not px.ledger.exists()


class TestRefusal:
    def test_a_refused_run_keeps_its_usage_and_holds_no_findings(self, px):
        px.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        px.ok(500, "gate", "--refusal", "stale: the head moved after the launch")
        row = px.only_row()
        assert row["findings"] == []
        assert row["status"]["fields"]["findings"]["status"] == "refused"
        assert row["refusal"] == "stale: the head moved after the launch"
        assert row["cost"]["usage_delta"]["delta"] == 2.0

    def test_a_later_harvest_keeps_the_refusal(self, px):
        px.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        px.ok(500, "gate", "--refusal", "raced")
        px.harvest()
        assert px.only_row()["findings"] == []
        assert px.only_row()["status"]["fields"]["findings"]["status"] == "refused"

    def test_an_empty_refusal_reason_is_refused(self, px):
        px.record(500)
        assert px.append(500, "gate", "--refusal", " ").returncode == 2
        assert not px.ledger.exists()


class TestFlags:
    @pytest.mark.parametrize("flags, rtype, mutation, message", [
        (["--refusal", "x", "--cache", "CACHE"], "spec", False, "unrecognized arguments: --refusal x"),
        (["--refusal", "x"], "witness-mutation", True, "unrecognized arguments: --refusal x"),
        (["--skip-reason", "x"], "witness-mutation", True, "unrecognized arguments: --skip-reason x")])
    def test_refusal_is_for_codex_types_and_skip_reason_for_codex_types_and_the_review_axes(
            self, px, flags, rtype, mutation, message):
        # #1401: the axes may be skipped (the ablation), so `spec` + --skip-reason is a row, not a refusal.
        # OE3 (#1406): each type's parser holds only its own flags, so argparse names the foreign one.
        flags = [str(px.cache) if a == "CACHE" else a for a in flags]
        extra = ["--mutation-id", "m1", "--outcome", "red", "--seconds", "1"] if mutation else []
        r = px.run("append", "--repo", "skills", "--ticket", 500, "--type", rtype,
                   "--ledger", px.ledger, *flags, *extra)
        assert r.returncode == 2, (rtype, flags)
        assert message in r.stderr
        assert not px.ledger.exists()

    def test_mutation_flags_are_refused_on_a_codex_type_by_the_guard_not_a_missing_cache(self, px):
        px.record(500, before=f"1 {W1}", after=f"2 {W1}")
        r = px.append(500, "gate", "--mutation-id", "m1", "--outcome", "red", "--seconds", 3)
        assert r.returncode == 2
        assert "append --type codex-gate: error: unrecognized arguments: --mutation-id m1" in r.stderr
        assert not px.ledger.exists()

    def test_a_codex_row_is_round_one(self, px):
        px.record(500)
        r = px.append(500, "gate", "--round", "2")
        assert r.returncode == 2
        assert "unrecognized arguments: --round 2" in r.stderr


class TestAudit:
    """`append --type codex-audit` (#1361): the weekly audit's one run over the PRs that skipped the gate."""
    PRS, RANGE = [101, 104, 107], "aaa..bbb"

    def audit_record(self, px, before=f"10 {W1}", after=f"14 {W1}", out=OUT_TWO, status=0, name="2026-10-09",
                     drop=(), **fields):
        """An audit record at its own path per `name`; `fields` replace its values, `drop` removes keys."""
        rec = {"prs": self.PRS, "range": self.RANGE, "status": status, "started": STARTED, "completed": COMPLETED,
               "usage_before": before, "usage_after": after, **fields}
        for key in drop:
            rec.pop(key)
        path = px.skills / f"codex-audit-{name}.json"
        px.skills.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec) + "\n")
        if out is not None:
            path.with_suffix(".out").write_text(out)
        return path

    def audit(self, px, *extra):
        return px.run("append", "--repo", "skills", "--type", "codex-audit", "--ledger", px.ledger, *extra)

    def report(self, px):
        r = px.run("report", "--ledger", px.ledger, "--format", "json")
        assert r.returncode == 0, r.stderr
        return {t["type"]: t for t in json.loads(r.stdout)["types"]}

    def test_an_audit_row_holds_its_prs_range_usage_change_and_findings(self, px):
        r = self.audit(px, "--record", self.audit_record(px))
        assert r.returncode == 0, r.stderr
        row = px.only_row()
        assert (row["type"], row["prs"], row["range"]) == ("codex-audit", self.PRS, self.RANGE)
        assert row["cost"]["usage_delta"] == {"status": "known", "before": 10.0, "after": 14.0, "delta": 4.0}
        assert row["cost"]["wall_clock"]["seconds"] == 150
        assert [f["severity"] for f in row["findings"]] == ["high", "medium"]
        assert row["status"]["fields"]["findings"] == {"status": "known"}

    def test_the_report_counts_an_audit_under_its_own_audit_column(self, px):
        self.audit(px, "--record", self.audit_record(px))
        px.record(500, before=f"1 {W1}", after=f"2 {W1}")
        px.ok(500, "gate")
        types = self.report(px)
        assert (types["codex-audit"]["rows"], types["codex-audit"]["audited_prs"]) == (1, 3)
        assert types["codex-audit"]["usage_percent"] == 4.0
        assert types["codex-gate"]["audited_prs"] is None
        md = px.run("report", "--ledger", px.ledger).stdout
        header = [c.strip() for c in md.splitlines()[0].strip("|").split("|")]
        (audit_line,) = [line for line in md.splitlines() if line.startswith("| codex-audit |")]
        cells = [c.strip() for c in audit_line.strip("|").split("|")]
        assert cells[header.index("audited PRs")] == "3"

    @pytest.mark.parametrize("before, after, why", [(None, f"14 {W1}", "before reading missing"),
                                                    (f"10 {W1}", f"1 {W2}", "different windows"),
                                                    (f"10 {W1}", f"9 {W1}", "usage fell")])
    def test_usage_change_follows_the_two_reading_rule(self, px, before, after, why):
        self.audit(px, "--record", self.audit_record(px, before=before, after=after))
        delta = px.only_row()["cost"]["usage_delta"]
        assert delta["status"] == "unknown", why
        assert why in delta["reason"]

    def test_an_audit_that_failed_is_a_refusal_with_no_findings(self, px):
        self.audit(px, "--record", self.audit_record(px, status=1, out=OUT_REFUSED))
        row = px.only_row()
        assert (row["findings"], row["status"]["fields"]["findings"]["status"]) == ([], "refused")
        self.audit(px, "--record", self.audit_record(px), "--refusal", "range moved")
        row = px.only_row()
        assert (row["findings"], row["refusal"]) == ([], "range moved")
        assert row["cost"]["usage_delta"]["delta"] == 4.0
        assert self.report(px)["codex-audit"]["refused_rows"] == 1

    def test_an_audit_record_reads_its_status_as_a_gate_record_does(self, px):
        """One record-to-status rule for both Codex row kinds: a failed run's refusal quotes the Codex
        error line, and a status that is not an integer is never a clean run."""
        self.audit(px, "--record", self.audit_record(px, status=1, out=OUT_REFUSED))
        assert px.only_row()["status"]["fields"]["findings"]["reason"] == \
            "exit status 1: You've hit your usage limit. Try again at Oct 3rd."
        px.ledger.unlink()
        self.audit(px, "--record", self.audit_record(px, status=False))
        row = px.only_row()
        assert (row["findings"], row["status"]["fields"]["findings"]["status"]) == ([], "refused")

    def test_an_unreadable_out_is_unknown_never_a_clean_audit(self, px):
        self.audit(px, "--record", self.audit_record(px, out=None))
        assert px.only_row()["status"]["fields"]["findings"]["status"] == "unknown"
        assert self.report(px)["codex-audit"]["clean_rows"] == 0

    def test_an_audit_not_launched_is_a_skipped_row(self, px):
        r = self.audit(px, "--skip-reason", "ceiling")
        assert r.returncode == 0, r.stderr
        row = px.only_row()
        assert (row["type"], row["skip_reason"], row["cost"]["usage_delta"]["delta"]) == ("codex-audit", "ceiling", 0)
        assert self.report(px)["codex-audit"]["skipped_rows"] == 1

    def test_a_later_harvest_keeps_the_audit_row(self, px):
        self.audit(px, "--record", self.audit_record(px))
        px.record(500, before=f"1 {W1}", after=f"2 {W1}")  # harvest refuses a cache with no record at all
        px.harvest()
        (row,) = [r for r in px.rows().values() if r["type"] == "codex-audit"]
        assert row["prs"] == self.PRS

    def test_a_bad_audit_append_is_refused_by_its_own_guard_and_writes_nothing(self, px):
        good = self.audit_record(px)
        cases = [
            (["--record", good, "--ticket", "500"], "unrecognized arguments: --ticket 500"),
            (["--record", good, "--cache", px.cache], "unrecognized arguments: --cache"),
            (["--record", good, "--round", "2"], "unrecognized arguments: --round 2"),
            (["--record", good, "--seconds", "3"], "unrecognized arguments: --seconds 3"),
            ([], "exactly one of --record and --skip-reason"),
            (["--record", good, "--skip-reason", "x"], "exactly one of --record and --skip-reason"),
            (["--skip-reason", " "], "non-empty reason"),
            (["--record", px.tmp / "absent.json"], "absent.json"),
            (["--record", self.audit_record(px, name="prs-not-ints", prs=["101"])], "needs `prs`"),
            (["--record", self.audit_record(px, name="prs-missing", drop=("prs",))], "needs `prs`"),
            (["--record", self.audit_record(px, name="range-not-str", range=7)], "needs `prs`"),
            (["--record", good, "--refusal", " "], "--refusal needs the reason"),
        ]
        for extra, why in cases:
            r = self.audit(px, *extra)
            assert r.returncode == 2, extra
            assert "codex-audit: " in r.stderr, extra
            assert why in r.stderr, extra
        assert not px.ledger.exists()

    def test_a_record_with_no_status_is_refused_saying_so(self, px):
        self.audit(px, "--record", self.audit_record(px, drop=("status",)))
        fstatus = px.only_row()["status"]["fields"]["findings"]
        assert fstatus["status"] == "refused"
        assert "has no status" in fstatus["reason"]

    def test_a_pass_type_still_needs_its_ticket_and_takes_no_record(self, px):
        for extra, why in ((["--type", "codex-gate", "--skip-reason", "size"],
                            "append --type codex-gate: error: the following arguments are required: --ticket"),
                           (["--type", "spec", "--cache", px.cache],
                            "append --type spec: error: the following arguments are required: --ticket"),
                           (["--type", "codex-gate", "--ticket", "500", "--skip-reason", "size",
                             "--record", self.audit_record(px)], "unrecognized arguments: --record")):
            r = px.run("append", "--repo", "skills", "--ledger", px.ledger, *extra)
            assert r.returncode == 2, extra
            assert why in r.stderr
        assert not px.ledger.exists()
