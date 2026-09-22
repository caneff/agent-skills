//! Contract tests for the `merge-cleanup` binary, against scratch origins and
//! clones and the fake `gh`/`herdr` from `lane-fake` — the seam the bash
//! suite it replaces used. Covers every case in
//! `flow/bin/merge-cleanup.test.sh` except the `jq`-missing ones (the port
//! reads JSON itself), plus the regression tests for the bugs fixed in it.

mod support;
use support::cleanup::{Cleanup, Tools};

fn s(p: &std::path::Path) -> &str {
    p.to_str().unwrap()
}

// --- 1. dry run changes nothing ----------------------------------------------

#[test]
fn dry_run_leaves_branch_and_head_untouched() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let before = c.rev(&r, "HEAD");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--dry-run"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(c.has_branch(&r, "caneff/merged-one"));
    assert_eq!(c.rev(&r, "HEAD"), before);
}

// --- 2. an unmerged branch is refused, --force overrides ---------------------

#[test]
fn an_unmerged_branch_is_refused_and_force_cleans_it() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/open-one"], &[]);
    assert!(!run.ok && run.stderr.contains("caneff/open-one is not merged"), "{}", run.text());
    assert!(c.has_branch(&r, "caneff/open-one"));

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/open-one", "--force"], &[]);
    assert!(run.ok && run.has("--force: skipping the merged check for caneff/open-one"), "{}", run.text());
    assert!(!c.has_branch(&r, "caneff/open-one"));
}

#[test]
fn a_branch_with_commits_past_its_merged_prs_head_is_refused() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-then-more"], &[]);
    assert!(!run.ok && run.has("not merged"), "{}", run.text());
    assert!(c.has_branch(&r, "caneff/merged-then-more"));
}

// --- 3. the default branch is refused ----------------------------------------

#[test]
fn the_default_branch_is_refused() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "main"], &[]);
    assert!(!run.ok && run.stderr.contains("merge-cleanup: refusing to delete the default branch main"), "{}", run.text());
    assert!(c.has_branch(&r, "main"));
}

// --- 4. a real merge is deleted with -d, not -D ------------------------------

#[test]
fn a_fast_forward_merge_is_deleted_with_d() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/ff-merged"], &[]);
    assert!(run.ok && run.has("deleted local branch caneff/ff-merged"), "{}", run.text());
    assert!(!run.has("-D"), "{}", run.text());
}

// --- 5. the full run ---------------------------------------------------------

#[test]
fn the_full_run_deletes_both_branches_and_fast_forwards() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!c.has_branch(&r, "caneff/merged-one"));
    let origin = c.root().join("r1.origin.git");
    assert!(!c.has_branch(&origin, "caneff/merged-one"), "remote branch survived");
    assert_eq!(c.rev(&r, "main"), c.rev(&r, "origin/main"), "main not fast-forwarded");
    assert!(run.has("fast-forwarding main in"), "{}", run.text());

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--force"], &[]);
    assert!(run.has("skipped the local branch delete (no local caneff/merged-one)"), "{}", run.text());
    assert!(run.has("skipped the remote branch delete (origin has no caneff/merged-one)"), "{}", run.text());
}

#[test]
fn the_deleted_tip_is_recorded_under_refs_deleted_keyed_by_its_short_sha() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let tip = c.rev(&r, "caneff/merged-one");
    let short = c.git_out(&["-C", s(&r), "rev-parse", "--short", &tip]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok, "{}", run.text());
    let record = format!("refs/deleted/caneff/merged-one@{short}");
    assert_eq!(c.rev(&r, &record), tip);
    let line = format!("recorded the tip of caneff/merged-one at {record} (git branch caneff/merged-one {record} restores it)");
    assert!(run.stdout.contains(&line), "{}", run.text());
}

/// Every `refs/deleted/` record in `repo`, as `<ref> <sha>` lines.
fn deleted_records(c: &Cleanup, repo: &std::path::Path) -> Vec<String> {
    c.git_out(&["-C", s(repo), "for-each-ref", "--format=%(refname) %(objectname)", "refs/deleted/"]).lines().map(str::to_string).collect()
}

#[test]
fn nested_branch_names_do_not_collide_under_refs_deleted() {
    // #737: git cannot hold refs/deleted/foo and refs/deleted/foo/bar at once.
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    c.git_ok(&["-C", s(&r), "branch", "foo", "caneff/local-only"]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "foo", "--force"], &[]);
    assert!(run.ok && !c.has_branch(&r, "foo"), "{}", run.text());
    c.git_ok(&["-C", s(&r), "branch", "foo/bar", "caneff/open-one"]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "foo/bar", "--force"], &[]);
    assert!(run.ok && !c.has_branch(&r, "foo/bar"), "{}", run.text());
    let records = deleted_records(&c, &r);
    assert_eq!(records.len(), 2, "{records:?}");
    assert!(records.iter().any(|l| l.starts_with("refs/deleted/foo@") && l.ends_with(&c.rev(&r, "caneff/local-only"))), "{records:?}");
    assert!(records.iter().any(|l| l.starts_with("refs/deleted/foo/bar@") && l.ends_with(&c.rev(&r, "caneff/open-one"))), "{records:?}");
}

#[test]
fn deleting_a_branch_name_twice_keeps_both_tips() {
    // #737: the second delete of a name must not overwrite the first record.
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    for tip in ["caneff/local-only", "caneff/open-one"] {
        c.git_ok(&["-C", s(&r), "branch", "again", tip]);
        let run = c.mc(Tools::Full, &["--repo", s(&r), "again", "--force"], &[]);
        assert!(run.ok && !c.has_branch(&r, "again"), "{}", run.text());
    }
    let shas: Vec<String> = deleted_records(&c, &r).iter().map(|l| l.rsplit(' ').next().unwrap().to_string()).collect();
    let mut want = vec![c.rev(&r, "caneff/local-only"), c.rev(&r, "caneff/open-one")];
    let mut got = shas.clone();
    want.sort();
    got.sort();
    assert_eq!(got, want);
}

#[test]
fn a_record_that_cannot_be_written_says_so_and_keeps_the_branch() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let short = c.git_out(&["-C", s(&r), "rev-parse", "--short", "caneff/local-only"]);
    let lock = r.join(format!(".git/refs/deleted/caneff/local-only@{short}.lock"));
    std::fs::create_dir_all(lock.parent().unwrap()).unwrap();
    std::fs::write(&lock, "").unwrap();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/local-only", "--force"], &[]);
    let want = format!("merge-cleanup: could not record the tip of caneff/local-only at refs/deleted/caneff/local-only@{short}, so it was not deleted: ");
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    assert!(c.has_branch(&r, "caneff/local-only"));
}

#[test]
fn a_branch_git_calls_unmerged_falls_back_to_capital_d() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/local-only", "--force"], &[]);
    assert!(run.ok && run.has("with -D"), "{}", run.text());
    assert!(!c.has_branch(&r, "caneff/local-only"));
}

// --- 6. --pr and a PR URL resolve to the head branch -------------------------

#[test]
fn pr_flag_resolves_to_the_head_branch() {
    let c = Cleanup::new();
    let r = c.mkfixture("r2");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "--pr", "7"], &[]);
    assert!(run.ok && run.has("PR #7 is caneff/merged-one"), "{}", run.text());
    assert!(!c.has_branch(&r, "caneff/merged-one"));
}

#[test]
fn a_pr_url_resolves_to_the_head_branch() {
    let c = Cleanup::new();
    let r = c.mkfixture("r3");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "https://github.com/caneff/agent-skills/pull/7"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!c.has_branch(&r, "caneff/merged-one"));
}

#[test]
fn a_bare_number_is_a_pr_and_a_number_with_letters_is_a_branch() {
    let c = Cleanup::new();
    let r = c.mkfixture("r2");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "8"], &[]);
    assert!(!run.ok && run.stderr.contains("merge-cleanup: could not read PR #8"), "{}", run.text());
    let run = c.mc(Tools::Full, &["--repo", s(&r), "8x"], &[]);
    assert!(!run.ok && run.stderr.contains("8x is not merged"), "{}", run.text());
}

// --- 7. without gh, the ancestor test decides --------------------------------

#[test]
fn without_gh_an_ancestor_branch_is_cleaned_and_a_squash_is_refused() {
    let c = Cleanup::new();
    let r = c.mkfixture("r4");
    let run = c.mc(Tools::NoGh, &["--repo", s(&r), "caneff/ff-merged"], &[]);
    assert!(run.ok && !c.has_branch(&r, "caneff/ff-merged"), "{}", run.text());
    let run = c.mc(Tools::NoGh, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
}

// --- 8. a closed ticket's in-progress label and assignee are cleared --------

#[test]
fn a_closed_tickets_in_progress_label_and_assignee_are_cleared() {
    let c = Cleanup::new();
    let r = c.mkfixture("r5");
    c.mk_implement_branch(&r, "42");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-42"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff")],
    );
    assert!(run.ok, "{}", run.text());
    assert!(run.has("clearing #42's in-progress label and assignee"), "{}", run.text());
    assert!(c.calls().contains("gh issue edit 42"), "{}", c.calls());
    assert!(c.calls().contains("--remove-label in-progress"), "{}", c.calls());
    assert!(c.calls().contains("--remove-assignee caneff"), "{}", c.calls());
}

#[test]
fn every_actual_assignee_is_removed_not_just_the_callers_own_login() {
    // #829 Codex pass: `--remove-assignee @me` clears only the identity
    // running cleanup, so a ticket reassigned to someone else kept its
    // assignee. Read the issue's real assignees and remove those.
    let c = Cleanup::new();
    let r = c.mkfixture("r10");
    c.mk_implement_branch(&r, "47");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-47"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "alice,bob")],
    );
    assert!(run.ok, "{}", run.text());
    assert!(c.calls().contains("--remove-assignee alice,bob"), "{}", c.calls());
    assert!(!c.calls().contains("@me"), "{}", c.calls());
}

#[test]
fn a_closed_ticket_with_no_assignee_only_removes_the_label() {
    let c = Cleanup::new();
    let r = c.mkfixture("r11");
    c.mk_implement_branch(&r, "48");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "implement-48"], &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "")]);
    assert!(run.ok, "{}", run.text());
    assert!(c.calls().contains("gh issue edit 48 --repo") && c.calls().contains("--remove-label in-progress"), "{}", c.calls());
    assert!(!c.calls().contains("--remove-assignee"), "{}", c.calls());
}

#[test]
fn a_failed_edit_exits_non_zero_and_names_the_exact_command_to_re_run() {
    // #829 Codex pass found the edit's result was discarded, so an API
    // failure after the branch and worktree are already gone reported
    // success with no way to repair the claim later. #832: that was still
    // wrong — the caller must see non-zero, with a message distinguishing
    // "git cleanup completed" from "claim clearing failed, re-run this".
    let c = Cleanup::new();
    let r = c.mkfixture("r12");
    c.mk_implement_branch(&r, "49");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-49"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff"), ("GH_ISSUE_EDIT_FAIL", "49")],
    );
    assert!(!run.ok, "{}", run.text());
    assert!(!c.has_branch(&r, "implement-49"), "{}", run.text());
    assert!(
        run.stderr.contains("git cleanup completed, but could not clear #49's in-progress label and assignee"),
        "{}",
        run.text()
    );
    assert!(
        run.stderr.contains("re-run: gh issue edit 49 --repo") && run.stderr.contains("--remove-label in-progress --remove-assignee caneff"),
        "{}",
        run.text()
    );
}

#[test]
fn a_failed_claim_clear_still_reports_stale_siblings() {
    // Review round on #832 (standards/correctness axes): folding the
    // claim-clear failure into cleanup_branch's own bool made `ok` mean
    // "either step failed", which silently skipped the stale report on a
    // run whose git cleanup fully succeeded.
    let c = Cleanup::new();
    let r = c.mkfixture("r13");
    c.mk_implement_branch(&r, "50");
    let wts = r.join(".claude/worktrees");
    c.worktree_add(&r, &["--detach", s(&wts.join("agent-old")), "origin/main"]);
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-50"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff"), ("GH_ISSUE_EDIT_FAIL", "50")],
    );
    assert!(!run.ok, "{}", run.text());
    assert!(!c.has_branch(&r, "implement-50"), "{}", run.text());
    assert!(run.stale().contains(&wts.join("agent-old").display().to_string()), "{}", run.text());
}

#[test]
fn a_sweep_row_for_a_claim_clear_failure_says_so_distinctly_and_still_fails_the_run() {
    // Same round: the sweep table mapped this case to "FAILED", which reads
    // as "the branch survived" — exactly what the new stderr line exists to
    // rule out. A branch git fully cleaned gets its own verdict, not the
    // one used for a branch that is still there.
    let c = Cleanup::new();
    let other = c.mkfixture("src2/other");
    c.mk_implement_branch(&other, "51");
    let root = other.parent().unwrap().to_path_buf();
    let run = c.mc(
        Tools::Full,
        &["--sweep", "--root", s(&root), "--yes"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff"), ("GH_ISSUE_EDIT_FAIL", "51")],
    );
    assert!(!run.ok, "{}", run.text());
    assert!(!c.has_branch(&other, "implement-51"), "{}", run.text());
    let rows: Vec<&str> = run.stdout.lines().skip_while(|l| *l != "sweep summary").skip(1).take_while(|l| l.starts_with("  ")).collect();
    assert!(rows.iter().any(|r| r.contains("implement-51") && r.contains("claim not cleared") && !r.contains("FAILED")), "{rows:#?}");
}

#[test]
fn a_denied_remote_delete_is_reported_non_success_but_still_clears_the_claim() {
    // Codex pass on PR #842: `step()`'s result on `git push origin --delete`
    // was discarded, so a denied delete (branch protection, a race) left
    // the remote branch alive while merge-cleanup still exited 0 and, worse,
    // would have told an operator "git cleanup completed" on a run where it
    // hadn't. The PR merged either way, so the claim still clears.
    let c = Cleanup::new();
    let r = c.mkfixture("r14");
    c.mk_implement_branch(&r, "52");
    let origin = c.root().join("r14.origin.git");
    c.git_ok(&["-C", s(&origin), "config", "receive.denyDeletes", "true"]);
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-52"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff")],
    );
    assert!(!run.ok, "{}", run.text());
    assert!(c.has_branch(&origin, "implement-52"), "the denied delete should have left the remote branch");
    assert!(
        run.stderr.contains("could not delete remote branch implement-52; re-run: git")
            && run.stderr.contains("push origin --delete implement-52"),
        "{}",
        run.text()
    );
    assert!(c.calls().contains("gh issue edit 52") && c.calls().contains("--remove-label in-progress"), "{}", c.calls());
}

#[test]
fn a_denied_remote_delete_changes_the_claim_clear_failure_wording() {
    // Same pass: the claim-clear failure message unconditionally said "git
    // cleanup completed", which would be false when the remote delete also
    // failed — an operator reading it would think only the label needed a
    // re-run, missing the branch still on origin.
    let c = Cleanup::new();
    let r = c.mkfixture("r15");
    c.mk_implement_branch(&r, "53");
    let origin = c.root().join("r15.origin.git");
    c.git_ok(&["-C", s(&origin), "config", "receive.denyDeletes", "true"]);
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-53"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff"), ("GH_ISSUE_EDIT_FAIL", "53")],
    );
    assert!(!run.ok, "{}", run.text());
    assert!(
        run.stderr.contains(
            "git cleanup did not fully complete (the remote branch delete also failed), but could not clear #53's in-progress label and assignee"
        ),
        "{}",
        run.text()
    );
    assert!(!run.stderr.contains("git cleanup completed, but could not clear #53"), "{}", run.text());
}

#[test]
fn a_sweep_row_for_a_denied_remote_delete_says_so_distinctly_and_still_fails_the_run() {
    let c = Cleanup::new();
    let other = c.mkfixture("src3/other");
    c.mk_implement_branch(&other, "54");
    let origin_dir = other.parent().unwrap().join("other.origin.git");
    c.git_ok(&["-C", s(&origin_dir), "config", "receive.denyDeletes", "true"]);
    let root = other.parent().unwrap().to_path_buf();
    let run = c.mc(
        Tools::Full,
        &["--sweep", "--root", s(&root), "--yes"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff")],
    );
    assert!(!run.ok, "{}", run.text());
    assert!(c.has_branch(&origin_dir, "implement-54"), "the denied delete should have left the remote branch");
    let rows: Vec<&str> = run.stdout.lines().skip_while(|l| *l != "sweep summary").skip(1).take_while(|l| l.starts_with("  ")).collect();
    assert!(rows.iter().any(|r| r.contains("implement-54") && r.contains("remote branch not deleted") && !r.contains("FAILED")), "{rows:#?}");
}

// --- 8b. a clump: every ticket the merged PR closes (#889) ------------------

#[test]
fn every_ticket_the_merged_pr_closes_has_its_claim_cleared() {
    // A clump lands as one PR closing several tickets. Before #889 only the
    // branch's own ticket was cleared and the rest kept a stale in-progress
    // label and assignee, cleared by hand — six of them on one trial clump.
    let c = Cleanup::new();
    let r = c.mkfixture("r20");
    c.mk_implement_branch(&r, "60");
    c.record_pr_closes("7", &["60", "61", "62"]);
    let closed = ("CLOSED\tin-progress\tcaneff", "");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-60"],
        &[("GH_ISSUE_60", closed.0), ("GH_ISSUE_61", closed.0), ("GH_ISSUE_62", closed.0), ("GH_STATE", closed.1)],
    );
    assert!(run.ok, "{}", run.text());
    for n in ["60", "61", "62"] {
        assert!(c.calls().contains(&format!("gh issue edit {n} --repo")), "#{n} was not cleared: {}", c.calls());
        assert!(run.has(&format!("clearing #{n}'s in-progress label and assignee")), "{}", run.text());
    }
    assert!(run.has("cleared #60, #61, #62"), "{}", run.text());
}

#[test]
fn a_clump_with_mixed_width_ticket_numbers_clears_in_ascending_numeric_order() {
    // #983: the comment on the sort claims length-then-text is why the keys
    // are digit strings, but no fixture had mixed widths to prove it. "10"
    // sorts before "9" lexicographically; a plain `tickets.sort()` would
    // report "cleared #10, #9" here.
    let c = Cleanup::new();
    let r = c.mkfixture("r20c");
    c.mk_implement_branch(&r, "9");
    c.record_pr_closes("7", &["9", "10"]);
    let closed = ("CLOSED\tin-progress\tcaneff", "");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-9"],
        &[("GH_ISSUE_9", closed.0), ("GH_ISSUE_10", closed.0), ("GH_STATE", closed.1)],
    );
    assert!(run.ok, "{}", run.text());
    assert!(run.has("cleared #9, #10"), "{}", run.text());
}

#[test]
fn a_branch_number_too_long_for_a_u64_still_has_its_claim_cleared() {
    // #903: the ticket set is digit strings, not parsed numbers, because
    // merge-cleanup reads an existing branch name and must not drop it.
    // 23 digits: past u64::MAX (20 digits, 18446744073709551615).
    let n = "12345678901234567890123";
    let c = Cleanup::new();
    let r = c.mkfixture("r20b");
    c.mk_implement_branch(&r, n);
    let key = format!("GH_ISSUE_{n}");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), &format!("implement-{n}")],
        &[(key.as_str(), "CLOSED\tin-progress\tcaneff"), ("GH_STATE", "")],
    );
    assert!(run.ok, "{}", run.text());
    assert!(run.has(&format!("clearing #{n}'s in-progress label and assignee")), "{}", run.text());
    assert!(c.calls().contains(&format!("gh issue edit {n} --repo")), "{}", c.calls());
}

#[test]
fn a_clump_ticket_in_another_repo_is_never_edited() {
    // closingIssuesReferences can name an issue in another repo, and every
    // edit here goes out with this repo's --repo: editing that number here
    // would hit an unrelated issue that happens to share it.
    let c = Cleanup::new();
    let r = c.mkfixture("r21");
    c.mk_implement_branch(&r, "63");
    c.record_pr_closes("7", &["63", "caneff/elsewhere#64"]);
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-63"],
        &[("GH_ISSUE_63", "CLOSED\tin-progress\tcaneff"), ("GH_ISSUE_64", "CLOSED\tin-progress\tcaneff")],
    );
    assert!(run.ok, "{}", run.text());
    assert!(c.calls().contains("gh issue edit 63 --repo"), "{}", c.calls());
    assert!(!c.calls().contains("gh issue edit 64"), "{}", c.calls());
    // Named, not silently dropped: a claim this run leaves alone has to say so.
    assert!(run.has("skipped clearing caneff/elsewhere#64 (another repo"), "{}", run.text());
}

#[test]
fn a_clump_ticket_still_open_is_left_alone_while_its_siblings_clear() {
    let c = Cleanup::new();
    let r = c.mkfixture("r22");
    c.mk_implement_branch(&r, "65");
    c.record_pr_closes("7", &["65", "66"]);
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-65"],
        &[("GH_ISSUE_65", "CLOSED\tin-progress\tcaneff"), ("GH_ISSUE_66", "OPEN\tin-progress\tcaneff")],
    );
    assert!(run.ok, "{}", run.text());
    assert!(c.calls().contains("gh issue edit 65 --repo"), "{}", c.calls());
    assert!(!c.calls().contains("gh issue edit 66"), "{}", c.calls());
}

#[test]
fn one_clump_tickets_failed_edit_fails_the_run_and_names_only_that_ticket() {
    let c = Cleanup::new();
    let r = c.mkfixture("r23");
    c.mk_implement_branch(&r, "67");
    c.record_pr_closes("7", &["67", "68"]);
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-67"],
        &[("GH_ISSUE_67", "CLOSED\tin-progress\tcaneff"), ("GH_ISSUE_68", "CLOSED\tin-progress\tcaneff"), ("GH_ISSUE_EDIT_FAIL", "68")],
    );
    assert!(!run.ok, "{}", run.text());
    assert!(run.stderr.contains("could not clear #68's in-progress label and assignee"), "{}", run.text());
    assert!(!run.stderr.contains("could not clear #67"), "{}", run.text());
    assert!(c.calls().contains("gh issue edit 67 --repo"), "the sibling still clears: {}", c.calls());
}

#[test]
fn a_failed_pr_list_fails_the_run_instead_of_reading_as_a_pr_that_closed_nothing() {
    // The clump's list could not be read, so the run does not get to say it
    // cleared the clump: an empty answer and a failed one must not look the
    // same, or the siblings stay claimed under a success report.
    let c = Cleanup::new();
    let r = c.mkfixture("r25");
    c.mk_implement_branch(&r, "70");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-70"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff"), ("GH_PR_CLOSES_FAIL", "fail")],
    );
    assert!(!run.ok, "a failed lookup must fail the run: {}", run.text());
    assert!(run.stderr.contains("could not read which tickets PR #7 closes (gh pr view failed)"), "{}", run.text());
    assert!(run.stderr.contains("re-run: gh pr view 7 --repo"), "the message names the read to redo: {}", run.text());
    // The branch's own ticket is still known, so it still clears.
    assert!(c.calls().contains("gh issue edit 70 --repo"), "{}", c.calls());
}

#[test]
fn an_unparseable_pr_list_answer_fails_the_run_too() {
    // Worse than a transient: a non-JSON answer is not retried into
    // correctness by anything else in the run.
    let c = Cleanup::new();
    let r = c.mkfixture("r26");
    c.mk_implement_branch(&r, "71");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-71"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff"), ("GH_PR_CLOSES_FAIL", "garbage")],
    );
    assert!(!run.ok, "{}", run.text());
    assert!(run.stderr.contains("answered something that is not JSON"), "{}", run.text());
}

#[test]
fn only_the_pr_that_landed_this_tip_decides_the_clump_not_every_pr_the_branch_name_ever_had() {
    // Branch names are reused. Unioning every merged PR on the name strips
    // labels and assignees off issues that belonged to an earlier landing —
    // tickets this run has no business unclaiming.
    let c = Cleanup::new();
    let r = c.mkfixture("r27");
    c.mk_implement_branch(&r, "72");
    // PR 7 is this landing, at the branch tip; PR 8 was an older landing on
    // the same name, at a sha this branch has moved past.
    c.record_pr_heads(&r, "implement-72", &[("8", "main"), ("7", "implement-72")]);
    c.record_pr_closes("7", &["72", "73"]);
    c.record_pr_closes("8", &["80", "81"]);
    let closed = "CLOSED\tin-progress\tcaneff";
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-72"],
        &[("GH_ISSUE_72", closed), ("GH_ISSUE_73", closed), ("GH_ISSUE_80", closed), ("GH_ISSUE_81", closed)],
    );
    assert!(run.ok, "{}", run.text());
    for n in ["72", "73"] {
        assert!(c.calls().contains(&format!("gh issue edit {n} --repo")), "this landing's #{n} was not cleared: {}", c.calls());
    }
    for n in ["80", "81"] {
        assert!(!c.calls().contains(&format!("gh issue edit {n}")), "an older landing's #{n} was cleared: {}", c.calls());
    }
}

#[test]
fn a_wrong_shape_pr_answer_fails_the_run_like_an_unparseable_one() {
    // Valid JSON of the wrong shape is the same defect as no JSON at all:
    // read as "closes nothing", it clears the branch ticket, reports success
    // and leaves the clump claimed.
    for (scenario, want) in [("wrong-shape", "no closingIssuesReferences array"), ("no-number", "a closing reference has no issue number")] {
        let c = Cleanup::new();
        let r = c.mkfixture(&format!("r28-{scenario}"));
        c.mk_implement_branch(&r, "74");
        let run = c.mc(
            Tools::Full,
            &["--repo", s(&r), "implement-74"],
            &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff"), ("GH_PR_CLOSES_FAIL", scenario)],
        );
        assert!(!run.ok, "{scenario}: {}", run.text());
        assert!(run.stderr.contains(want), "{scenario}: {}", run.text());
    }
}

#[test]
fn a_pr_that_closes_nothing_still_clears_the_branchs_own_ticket() {
    // A one-ticket PR whose closing reference never registered, and the
    // --force path where no merged PR was read at all: the branch name is
    // still the ticket, exactly as before #889.
    let c = Cleanup::new();
    let r = c.mkfixture("r24");
    c.mk_implement_branch(&r, "69");
    let run = c.mc(
        Tools::Full,
        &["--repo", s(&r), "implement-69"],
        &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress"), ("GH_ASSIGNEES", "caneff")],
    );
    assert!(run.ok, "{}", run.text());
    assert!(c.calls().contains("gh issue edit 69 --repo"), "{}", c.calls());
    assert!(
        !run.stdout.lines().any(|l| l.starts_with("cleared ")),
        "one ticket reports as it always did, with no clump summary line: {}",
        run.text()
    );
}

#[test]
fn an_open_tickets_label_and_assignee_are_left_alone() {
    let c = Cleanup::new();
    let r = c.mkfixture("r6");
    c.mk_implement_branch(&r, "43");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "implement-43"], &[("GH_STATE", "OPEN"), ("GH_LABELS", "in-progress")]);
    assert!(run.ok, "{}", run.text());
    assert!(!run.has("clearing #43"), "{}", run.text());
    assert!(!c.calls().contains("gh issue edit 43"), "{}", c.calls());
}

#[test]
fn a_closed_ticket_with_no_in_progress_label_is_left_alone() {
    // Already cleared, or never carried the label: nothing to remove, and
    // nothing for `gh issue edit` to error on over an undefined label.
    let c = Cleanup::new();
    let r = c.mkfixture("r7");
    c.mk_implement_branch(&r, "44");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "implement-44"], &[("GH_STATE", "CLOSED"), ("GH_LABELS", "bug")]);
    assert!(run.ok, "{}", run.text());
    assert!(!run.has("clearing #44"), "{}", run.text());
    assert!(!c.calls().contains("gh issue edit 44"), "{}", c.calls());
}

#[test]
fn a_failed_issue_read_is_reported_not_swallowed() {
    // GH_STATE unset is the fake's "no issue" failure, not an open issue —
    // the two must not look the same, or a real gh outage silently leaves
    // the stale claim #821 was filed over.
    let c = Cleanup::new();
    let r = c.mkfixture("r8");
    c.mk_implement_branch(&r, "45");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "implement-45"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(run.has("skipped clearing #45's in-progress label and assignee (gh issue view failed)"), "{}", run.text());
    assert!(!c.calls().contains("gh issue edit 45"), "{}", c.calls());
}

#[test]
fn a_spec_branchs_ticket_is_never_cleared() {
    let c = Cleanup::new();
    let r = c.mkfixture("r9");
    c.mk_implement_branch(&r, "spec-46");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "implement-spec-46"], &[("GH_STATE", "CLOSED"), ("GH_LABELS", "in-progress")]);
    assert!(run.ok, "{}", run.text());
    assert!(!run.has("clearing #"), "{}", run.text());
    assert!(!c.calls().contains("issue edit"), "{}", c.calls());
}

// --- argument handling -------------------------------------------------------

#[test]
fn help_prints_the_header_and_exits_zero() {
    let c = Cleanup::new();
    let run = c.mc(Tools::Full, &["--help"], &[]);
    assert!(run.ok);
    assert!(run.stdout.starts_with("The tail the controller runs after squash-merging a worker's PR"), "{}", run.stdout);
    assert!(run.stdout.contains("  merge-cleanup --sweep [--root <dir>] [--yes] [--dry-run]\n"), "{}", run.stdout);
    assert!(run.stdout.contains("`git branch <branch> refs/deleted/<branch>@<short sha>` restores."), "{}", run.stdout);
    assert!(run.stdout.contains("  merge-cleanup [--repo <path>] <branch|PR number|PR URL> [--force] [--discard] [--dry-run]\n"), "{}", run.stdout);
    assert!(run.stdout.contains("--discard removes it anyway"), "{}", run.stdout);
    assert!(run.stdout.contains("Ignored files include .scratch/"), "{}", run.stdout);
    assert!(run.stdout.contains("printed as cache file(s), distinct\nfrom the ignored file(s) count above"), "{}", run.stdout);
}

#[test]
fn help_states_the_cache_exemption_as_a_conjunction() {
    // #875: the help once read "or inside one whose own .gitignore is `*`", a
    // second independent way in. `is_cache` needs both: a name in CACHE_DIRS,
    // and — when that component is not the entry — a `*` .gitignore on it.
    let c = Cleanup::new();
    let run = c.mc(Tools::Full, &["--help"], &[]);
    assert!(run.ok);
    let flat = run.stdout.split_whitespace().collect::<Vec<_>>().join(" ");
    assert!(!flat.contains("or inside one whose own .gitignore is `*`"), "{flat}");
    // The name list is built from CACHE_DIRS, so this pins the sentence to
    // the const: a name added or dropped there changes it and reddens this.
    assert!(!flat.contains("{cache_names}"), "{flat}");
    let sentence = "named node_modules, __pycache__, target, .venv, .pytest_cache, .ruff_cache or .mypy_cache and,";
    assert!(flat.contains(sentence), "{flat}");
    assert!(flat.contains("Both are required"), "{flat}");
    assert!(flat.contains("a `*` .gitignore alone makes nothing a cache"), "{flat}");
}

#[test]
fn a_star_gitignore_alone_does_not_make_an_ignored_directory_a_cache() {
    // The rule the help states: a directory not named in CACHE_DIRS that
    // ignores itself wholly is still work.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r31", "implement-31");
    std::fs::create_dir_all(wt.join("build")).unwrap();
    std::fs::write(wt.join("build/.gitignore"), "*\n").unwrap();
    std::fs::write(wt.join("build/out.bin"), "evidence\n").unwrap();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.stderr.contains("ignored file(s) would be lost"), "{}", run.text());
    assert!(wt.join("build/out.bin").is_file(), "{}", run.text());
}

#[test]
fn argument_refusals_exit_one_with_their_message() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let cases: &[(&[&str], &str)] = &[
        (&["--bogus"], "merge-cleanup: unknown flag: --bogus"),
        (&["--repo", s(&r), "a", "b"], "merge-cleanup: one branch at a time"),
        (&["--repo", s(&r)], "merge-cleanup: name a branch, a PR number or URL, or pass --sweep"),
        (&["--repo", "/nonexistent-repo", "x"], "merge-cleanup: not a git repo: /nonexistent-repo"),
        (&["--sweep", "x"], "merge-cleanup: --sweep takes no branch or PR"),
        (&["--sweep", "--root", "/nonexistent-root"], "merge-cleanup: no such root: /nonexistent-root"),
    ];
    for (args, want) in cases {
        let run = c.mc(Tools::Full, args, &[]);
        assert!(!run.ok && run.stderr.trim_end() == *want, "{args:?}: {}", run.text());
    }
}

// --- 8. without herdr, a linked worktree is removed anyway -------------------

#[test]
fn without_herdr_the_linked_worktree_is_removed_and_the_skip_reported() {
    let c = Cleanup::new();
    let r = c.mkfixture("r5");
    let wt = c.root().join("r5-wt");
    c.worktree_add(&r, &[s(&wt), "caneff/merged-one"]);
    let run = c.mc(Tools::NoHerdr, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !c.has_branch(&r, "caneff/merged-one") && !wt.exists(), "{}", run.text());
    assert!(run.has(&format!("removing the linked worktree at {}", wt.display())), "{}", run.text());
    assert!(run.has("skipped the herdr agent check (herdr is not on PATH)"), "{}", run.text());
    assert!(run.has("skipped the herdr workspace close (herdr is not on PATH)"), "{}", run.text());
}

// --- #964: the controller/worker record is cleared with the workspace ------

fn worker_record(workspace: &std::path::Path, branch: &str) -> lane::workers::WorkerRecord {
    lane::workers::WorkerRecord {
        agent: "a".into(),
        tickets: vec!["1".into()],
        branch: branch.into(),
        workspace: workspace.display().to_string(),
        repo: "caneff/r5b".into(),
        cleanup: "cd x && merge-cleanup y --repo x".into(),
        chris_merges: false,
        dispatched_at: "".into(),
        proc_start: "1234567".into(),
    }
}

#[test]
fn a_removed_worktree_clears_its_worker_record_and_leaves_an_unrelated_one() {
    let c = Cleanup::new();
    let r = c.mkfixture("r5b");
    let wt = c.root().join("r5b-wt");
    c.worktree_add(&r, &[s(&wt), "caneff/merged-one"]);

    lane::workers::append(&c.home(), "111", &worker_record(&wt, "caneff/merged-one")).unwrap();
    let elsewhere = c.root().join("elsewhere-wt");
    lane::workers::append(&c.home(), "222", &worker_record(&elsewhere, "caneff/other")).unwrap();

    let run = c.mc(Tools::NoHerdr, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !wt.exists(), "{}", run.text());
    assert!(run.has(&format!("cleared the controller's worker record for {}", wt.display())), "{}", run.text());
    assert!(lane::workers::read(&c.home(), "111").is_empty(), "the removed workspace's record should be gone");
    assert_eq!(lane::workers::read(&c.home(), "222").len(), 1, "an unrelated controller's record must survive");
}

#[test]
fn a_dry_run_removal_leaves_the_worker_record_in_place() {
    let c = Cleanup::new();
    let r = c.mkfixture("r5c");
    let wt = c.root().join("r5c-wt");
    c.worktree_add(&r, &[s(&wt), "caneff/merged-one"]);
    lane::workers::append(&c.home(), "111", &worker_record(&wt, "caneff/merged-one")).unwrap();

    let run = c.mc(Tools::NoHerdr, &["--repo", s(&r), "caneff/merged-one", "--dry-run"], &[]);
    assert!(run.ok && wt.exists(), "{}", run.text());
    assert!(!run.has("cleared the controller's worker record"), "{}", run.text());
    assert_eq!(lane::workers::read(&c.home(), "111").len(), 1, "a dry run must not touch the record");
}

// --- 10. the live-session guard ----------------------------------------------

/// The bash suite's r6 fixture: a workspace at the lane's own path holding
/// the merged branch.
fn lane_workspace(c: &Cleanup, rel: &str, name: &str) -> (std::path::PathBuf, std::path::PathBuf) {
    let r = c.mkfixture(rel);
    let wt = r.join(".claude/worktrees").join(name);
    c.worktree_add(&r, &[s(&wt), "caneff/merged-one"]);
    (r, wt)
}

fn me() -> u32 {
    std::process::id()
}

/// This test process's own `/proc` starttime, for a registry fixture whose
/// pid is `me()` to read as live (`live_in` now checks `procStart` matches).
fn me_start() -> String {
    lane::proc_info::read_stat(me() as i32).unwrap().start
}

#[test]
fn a_live_registry_pid_in_the_workspace_refuses() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r6", "implement-1");
    c.session("live", &format!(r#"{{"pid":{},"cwd":"{}","procStart":"{}"}}"#, me(), wt.display(), me_start()));
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    let want = format!("merge-cleanup: refusing to remove {} — a live session is in it: pid {}", wt.display(), me());
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    assert!(wt.is_dir() && c.has_branch(&r, "caneff/merged-one"));
}

#[test]
fn a_herdr_agent_in_the_workspace_with_no_status_refuses() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r6", "implement-1");
    c.set_agents(&format!(r#"[{{"name":"skills-1","pane_id":"w2:p1","cwd":"{}"}}]"#, wt.display()));
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.stderr.contains("a live session is in it: herdr agent skills-1 (w2:p1)"), "{}", run.text());
    assert!(wt.is_dir());
}

#[test]
fn a_herdr_that_cannot_list_its_agents_refuses() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r6", "implement-1");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[("HERDR_FAIL", "1")]);
    let want = format!("merge-cleanup: refusing to remove {} — herdr agent list failed", wt.display());
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    assert!(wt.is_dir());
}

/// The r6 siblings: an idle leftover, one with work ahead of main, one with a
/// live session, one dirty, one holding only ignored files, a folder git no
/// longer tracks, plus a live pid and a herdr agent in a path that merely
/// starts with the workspace's, and a crashed session's registry file.
fn with_siblings(c: &Cleanup, r: &std::path::Path, wt: &std::path::Path) -> std::path::PathBuf {
    let wts = r.join(".claude/worktrees");
    c.worktree_add(r, &["--detach", s(&wts.join("agent-old")), "origin/main"]);
    c.worktree_add(r, &["-b", "ahead", s(&wts.join("agent-ahead")), "origin/main"]);
    std::fs::write(wts.join("agent-ahead/f"), "one\nahead\n").unwrap();
    c.git_ok(&["-C", s(&wts.join("agent-ahead")), "commit", "-qam", "ahead"]);
    c.worktree_add(r, &["--detach", s(&wts.join("agent-live")), "origin/main"]);
    c.worktree_add(r, &["--detach", s(&wts.join("agent-dirty")), "origin/main"]);
    std::fs::write(wts.join("agent-dirty/notes"), "unsaved\n").unwrap();
    std::fs::write(r.join(".git/info/exclude"), "scratch/\n").unwrap();
    c.worktree_add(r, &["--detach", s(&wts.join("agent-ignored")), "origin/main"]);
    std::fs::create_dir(wts.join("agent-ignored/scratch")).unwrap();
    std::fs::write(wts.join("agent-ignored/scratch/log"), "evidence\n").unwrap();
    c.session("sibling", &format!(r#"{{"pid":{},"cwd":"{}","procStart":"{}"}}"#, me(), wts.join("agent-live").display(), me_start()));
    c.session("prefix", &format!(r#"{{"pid":{},"cwd":"{}0","procStart":"{}"}}"#, me(), wt.display(), me_start()));
    c.set_agents(&format!(r#"[{{"name":"skills-10","pane_id":"w3:p1","cwd":"{}0"}}]"#, wt.display()));
    std::fs::create_dir(wts.join("agent-orphan")).unwrap();
    std::fs::write(wts.join("agent-orphan/f"), "leftover\n").unwrap();
    let mut child = std::process::Command::new("true").spawn().unwrap();
    let dead = child.id();
    child.wait().unwrap();
    c.session("dead", &format!(r#"{{"pid":{dead},"cwd":"{}"}}"#, wt.display()));
    c.set_workspaces_at(&[("w1", r), ("w9", wt)]);
    wts
}

#[test]
fn dry_run_finds_the_herdr_workspace_but_does_not_close_it() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r6", "implement-1");
    with_siblings(&c, &r, &wt);
    c.clear_calls();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--dry-run"], &[]);
    assert!(run.ok && wt.is_dir(), "{}", run.text());
    assert!(c.calls().contains("herdr workspace list") && !c.calls().contains("workspace close"), "{}", c.calls());
    assert!(run.has("would closing herdr workspace w9: herdr workspace close w9"), "{}", run.text());
}

#[test]
fn a_dead_pid_and_sessions_elsewhere_do_not_block_and_stale_siblings_are_listed() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r6", "implement-1");
    let wts = with_siblings(&c, &r, &wt);
    c.clear_calls();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());

    let calls = c.calls();
    assert!(calls.lines().any(|l| l == "herdr workspace close w9") && !calls.contains("close w1"), "{calls}");
    let stale_at = run.line_of("stale, not removed").expect("no stale report");
    assert!(run.line_of("closing herdr workspace w9").unwrap() > stale_at, "{}", run.text());

    let want = vec![wts.join("agent-old").display().to_string(), format!("{} (not a git worktree)", wts.join("agent-orphan").display())];
    assert_eq!(run.stale(), want, "{}", run.text());
    for d in ["agent-old", "agent-ahead", "agent-live", "agent-orphan"] {
        assert!(wts.join(d).is_dir(), "{d} was removed");
    }
}

#[test]
fn a_failed_worktree_removal_leaves_the_herdr_workspace_open() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r7", "implement-2");
    c.git_ok(&["-C", s(&r), "worktree", "lock", s(&wt)]);
    c.set_workspaces_at(&[("w5", &wt)]);
    c.clear_calls();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && wt.is_dir(), "{}", run.text());
    assert!(!c.calls().contains("workspace close"), "{}", c.calls());
}

#[test]
fn a_failure_after_the_removal_still_closes_the_herdr_workspace() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r9", "implement-4");
    std::fs::write(r.join(".git/refs/heads/caneff/merged-one.lock"), "").unwrap();
    c.set_workspaces_at(&[("w6", &wt)]);
    c.clear_calls();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && !wt.exists(), "{}", run.text());
    assert!(c.calls().lines().any(|l| l == "herdr workspace close w6"), "{}", c.calls());
}

#[test]
fn the_worktree_under_cleanup_is_not_a_stale_sibling() {
    let c = Cleanup::new();
    let r = c.mkfixture("r8");
    let wts = r.join(".claude/worktrees");
    c.worktree_add(&r, &[s(&wts.join("implement-3")), "caneff/ff-merged"]);
    c.worktree_add(&r, &["--detach", s(&wts.join("agent-old")), "origin/main"]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/ff-merged", "--dry-run"], &[]);
    assert!(run.ok, "{}", run.text());
    assert_eq!(run.stale(), vec![wts.join("agent-old").display().to_string()], "{}", run.text());
}

// --- 11. an idle herdr agent's pane is closed; working or blocked refuses ----

#[test]
fn an_idle_herdr_agents_pane_is_closed_and_the_cleanup_proceeds() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r10", "implement-5");
    c.set_agents(&format!(r#"[{{"name":"skills-idle","pane_id":"w7:p1","cwd":"{}","agent_status":"idle"}}]"#, wt.display()));
    c.set_workspaces_at(&[("w10", &wt)]);
    c.clear_calls();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    let calls = c.calls();
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
    assert!(calls.lines().any(|l| l == "herdr pane close w7:p1"), "{calls}");
    assert!(calls.lines().any(|l| l == "herdr workspace close w10"), "{calls}");
    assert!(run.has("closing idle herdr agent skills-idle's pane (w7:p1)"), "{}", run.text());
}

#[test]
fn a_done_herdr_agent_counts_as_idle() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r10", "implement-5");
    c.set_agents(&format!(r#"[{{"name":"skills-done","pane_id":"w7:p2","cwd":"{}/sub","agent_status":"done"}}]"#, wt.display()));
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !wt.exists(), "{}", run.text());
    assert!(c.calls().lines().any(|l| l == "herdr pane close w7:p2"), "{}", c.calls());
}

#[test]
fn a_working_or_blocked_herdr_agent_refuses() {
    for status in ["working", "blocked"] {
        let c = Cleanup::new();
        let (r, wt) = lane_workspace(&c, "r10", "implement-5");
        c.set_agents(&format!(r#"[{{"name":"skills-{status}","pane_id":"w8:p1","cwd":"{}","agent_status":"{status}"}}]"#, wt.display()));
        let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
        assert!(!run.ok && wt.is_dir() && c.has_branch(&r, "caneff/merged-one"), "{status}: {}", run.text());
        assert!(run.stderr.contains(&format!("herdr agent skills-{status} (w8:p1)")), "{}", run.text());
    }
}

#[test]
fn a_working_sibling_refuses_before_an_idle_agents_pane_is_closed() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r12", "implement-7");
    c.set_agents(&format!(
        r#"[{{"name":"skills-idle2","pane_id":"w9:p1","cwd":"{w}","agent_status":"idle"}},{{"name":"skills-working2","pane_id":"w9:p2","cwd":"{w}","agent_status":"working"}}]"#,
        w = wt.display()
    ));
    c.clear_calls();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && wt.is_dir() && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
    assert!(!c.calls().contains("herdr pane close"), "{}", c.calls());
}

#[test]
fn a_failed_herdr_pane_close_refuses_explicitly() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r13", "implement-8");
    c.set_agents(&format!(r#"[{{"name":"skills-stuck","pane_id":"w11:p1","cwd":"{}","agent_status":"idle"}}]"#, wt.display()));
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[("HERDR_PANE_CLOSE_FAIL", "w11:p1")]);
    let want = format!("merge-cleanup: refusing to remove {} — failed to close herdr agent skills-stuck's pane (w11:p1)", wt.display());
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    assert!(wt.is_dir() && c.has_branch(&r, "caneff/merged-one"));
}

#[test]
fn a_live_registry_pid_with_no_herdr_agent_still_refuses() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r11", "implement-6");
    c.session("r11", &format!(r#"{{"pid":{},"cwd":"{}","procStart":"{}"}}"#, me(), wt.display(), me_start()));
    let run = c.mc(Tools::NoHerdr, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.has(&format!("pid {}", me())) && wt.is_dir(), "{}", run.text());
}

/// #851: a registry record whose pid is alive but whose `procStart` doesn't
/// match that pid's own `/proc/<pid>/stat` starttime is a stale record from
/// a dead session whose pid has since been reused, not a live one — the
/// live-session guard must not refuse the removal over it.
#[test]
fn a_registry_pid_alive_but_reused_does_not_block_removal() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r17", "implement-851");
    c.session("r17", &format!(r#"{{"pid":{},"cwd":"{}","procStart":"not-the-real-start"}}"#, me(), wt.display()));
    let run = c.mc(Tools::NoHerdr, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn a_herdr_agent_with_no_name_refuses_whatever_its_status() {
    // An agent herdr cannot name cannot be classified, so it blocks — alone
    // and idle, or working behind a registry session it would explain.
    for (status, registry) in [("idle", false), ("working", true)] {
        let c = Cleanup::new();
        let (r, wt) = lane_workspace(&c, "r22", "implement-22");
        if registry {
            c.session("r22", &format!(r#"{{"pid":{},"cwd":"{}","sessionId":"sess-22"}}"#, me(), wt.display()));
        }
        c.set_agents(&format!(
            r#"[{{"pane_id":"w22:p1","cwd":"{}","agent_status":"{status}","agent_session":{{"value":"sess-22"}}}}]"#,
            wt.display()
        ));
        let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
        assert!(!run.ok && run.stderr.contains("a live session is in it: an unnamed herdr agent (w22:p1)"), "{status}: {}", run.text());
        assert!(wt.is_dir() && c.has_branch(&r, "caneff/merged-one"), "{status}");
        assert!(!c.calls().contains("pane close"), "{}", c.calls());
    }
}

// --- 12. a herdr worker's own registry session is decided by its status ------

#[test]
fn a_registry_session_matching_an_idle_herdr_agent_has_its_pane_closed() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r14", "implement-745a");
    c.session("r14", &format!(r#"{{"pid":{},"cwd":"{}","sessionId":"sess-14"}}"#, me(), wt.display()));
    c.set_agents(&format!(
        r#"[{{"name":"skills-14","pane_id":"w12:p1","cwd":"{}","agent_status":"idle","agent_session":{{"value":"sess-14"}}}}]"#,
        wt.display()
    ));
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
    assert!(c.calls().lines().any(|l| l == "herdr pane close w12:p1"), "{}", c.calls());
}

#[test]
fn a_registry_session_matching_a_working_herdr_agent_refuses() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r15", "implement-745b");
    c.session("r15", &format!(r#"{{"pid":{},"cwd":"{}","sessionId":"sess-15"}}"#, me(), wt.display()));
    c.set_agents(&format!(
        r#"[{{"name":"skills-15","pane_id":"w13:p1","cwd":"{}","agent_status":"working","agent_session":{{"value":"sess-15"}}}}]"#,
        wt.display()
    ));
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.stderr.contains("herdr agent skills-15 (w13:p1)") && wt.is_dir(), "{}", run.text());
}

#[test]
fn a_registry_session_with_no_matching_herdr_agent_refuses() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r16", "implement-745c");
    c.session("r16", &format!(r#"{{"pid":{},"cwd":"{}","sessionId":"sess-16-unmatched","procStart":"{}"}}"#, me(), wt.display(), me_start()));
    c.set_agents(&format!(
        r#"[{{"name":"skills-16","pane_id":"w14:p1","cwd":"{}","agent_status":"idle","agent_session":{{"value":"sess-other"}}}}]"#,
        wt.display()
    ));
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.stderr.contains(&format!("a live session is in it: pid {}", me())) && wt.is_dir(), "{}", run.text());
    assert!(!c.calls().contains("pane close"), "{}", c.calls());
}

// --- 9. sweep ----------------------------------------------------------------

/// The bash suite's sweep root: `other` holds merged branches, a stale
/// sibling and implement-9's workspace (with a herdr workspace w4);
/// `noremote` has a branch nothing can prove merged.
fn sweep_root(c: &Cleanup) -> std::path::PathBuf {
    let root = c.root().join("src");
    let other = c.mkfixture("src/other");
    let nr = root.join("noremote");
    std::fs::create_dir_all(&nr).unwrap();
    c.git_ok(&["init", "-q", "-b", "main", s(&nr)]);
    c.git_ok(&["-C", s(&nr), "config", "user.email", "t@example.com"]);
    c.git_ok(&["-C", s(&nr), "config", "user.name", "t"]);
    std::fs::write(nr.join("f"), "x\n").unwrap();
    c.git_ok(&["-C", s(&nr), "add", "f"]);
    c.git_ok(&["-C", s(&nr), "commit", "-qm", "x"]);
    c.git_ok(&["-C", s(&nr), "branch", "caneff/untracked"]);
    let wts = other.join(".claude/worktrees");
    c.worktree_add(&other, &["--detach", s(&wts.join("agent-old")), "origin/main"]);
    c.worktree_add(&other, &[s(&wts.join("implement-9")), "caneff/merged-one"]);
    c.set_workspaces_at(&[("w4", &wts.join("implement-9"))]);
    root
}

#[test]
fn a_dry_run_sweep_labels_its_plan_never_asks_and_deletes_nothing() {
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root), "--dry-run"], &[]);
    assert!(run.ok && run.stdout.lines().any(|l| l.starts_with("sweep plan (dry run): ")), "{}", run.text());
    assert!(!run.has("[y/N]"), "{}", run.text());
    assert!(c.has_branch(&root.join("other"), "caneff/merged-one"));
}

#[test]
fn a_sweep_with_stdin_not_a_terminal_prints_the_plan_refuses_and_deletes_nothing() {
    // #733: a closed or piped stdin is told apart from an answered no, and
    // no question is asked that nobody can answer.
    for piped in [None, Some("y\n")] {
        let c = Cleanup::new();
        let root = sweep_root(&c);
        let other = root.join("other");
        let args = ["--sweep", "--root", s(&root)];
        let run = match piped {
            None => c.mc(Tools::Full, &args, &[]),
            Some(input) => c.mc_piped(Tools::Full, &args, input),
        };
        assert!(!run.ok && run.stderr.contains("merge-cleanup: stdin is not a terminal; pass --yes"), "{}", run.text());
        assert!(!run.has("[y/N]") && !run.has("nothing deleted"), "{}", run.text());
        assert!(c.has_branch(&other, "caneff/merged-one") && other.join(".claude/worktrees/implement-9").is_dir(), "{}", run.text());
        assert!(run.has("  other caneff/merged-one  0 commits past PR #7"), "{}", run.text());
        assert!(run.has("merged branch(es) under") && !run.has("(dry run)"), "{}", run.text());
    }
}

#[test]
fn a_sweep_answered_n_at_the_terminal_deletes_nothing_reports_stale_and_exits_zero() {
    // #734: a deliberate no is not a failure, and still shows the stale list.
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let other = root.join("other");
    let run = c.mc_tty(Tools::Full, &["--sweep", "--root", s(&root)], "n\n");
    assert!(run.ok && run.terminal.contains("nothing deleted (answer y, or pass --yes)"), "{}", run.terminal);
    assert!(!run.terminal.contains("stdin is not a terminal"), "{}", run.terminal);
    let stale = format!("stale, not removed:\n  {}\n", other.join(".claude/worktrees/agent-old").display());
    assert!(run.stdout.contains(&stale), "{}", run.stdout);
    assert!(!run.stdout.contains("sweep summary") && !run.stdout.contains("== "), "{}", run.stdout);
    assert!(c.has_branch(&other, "caneff/merged-one") && other.join(".claude/worktrees/implement-9").is_dir());
    assert!(!c.calls().contains("close"), "{}", c.calls());
}

#[test]
fn a_sweep_with_yes_cleans_counts_and_reports() {
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let other = root.join("other");
    let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!c.has_branch(&other, "caneff/merged-one"), "{}", run.text());

    // The summary table, aligned the way `column -t` aligned it.
    let rows: Vec<&str> = run.stdout.lines().skip_while(|l| *l != "sweep summary").skip(1).take_while(|l| l.starts_with("  ")).collect();
    assert!(rows.contains(&"  other  caneff/merged-one  cleaned  0 commits past PR #7"), "{rows:#?}");
    assert!(rows.contains(&"  other  caneff/ff-merged   cleaned  0 commits past origin/main"), "{rows:#?}");

    let stale_at = run.line_of("stale, not removed").expect("no stale report");
    assert!(run.line_of("closing herdr workspace w4").unwrap() > stale_at, "{}", run.text());
    assert!(c.has_branch(&root.join("noremote"), "caneff/untracked") && !run.has("noremote caneff/untracked"), "{}", run.text());
    assert!(run.stale().contains(&other.join(".claude/worktrees/agent-old").display().to_string()), "{}", run.text());
    assert!(other.join(".claude/worktrees/agent-old").is_dir());
}

#[test]
fn a_sweep_piped_through_cat_still_shows_the_question_and_y_cleans() {
    // #733: the question goes to the terminal, not into the pipe.
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let run = c.mc_tty(Tools::Full, &["--sweep", "--root", s(&root)], "y\n");
    let question = "delete these branches and their worktrees? [y/N] ";
    assert!(run.ok && run.terminal.contains(question), "terminal: {}\npipe: {}", run.terminal, run.stdout);
    assert!(!run.stdout.contains("[y/N]") && run.stdout.contains("sweep summary"), "{}", run.stdout);
    assert!(!c.has_branch(&root.join("other"), "caneff/merged-one"));
}

#[test]
fn a_sweep_with_nothing_merged_says_so() {
    let c = Cleanup::new();
    let root = c.root().join("empty-src");
    std::fs::create_dir_all(&root).unwrap();
    let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root)], &[]);
    assert!(run.ok && run.has(&format!("sweep summary\n  nothing merged to clean up under {}", root.display())), "{}", run.text());
}

// --- 17. the fast-forward step rebuilds the lane binaries --------------------

fn lane_env(c: &Cleanup) -> (String, String) {
    let log = c.root().join("lane-install.log");
    let bin = c.root().join("installed-bin");
    std::fs::write(&log, "").unwrap();
    std::fs::write(&bin, "OLD\n").unwrap();
    (log.display().to_string(), bin.display().to_string())
}

#[test]
fn rebuilds_after_a_pull_that_changed_the_crate() {
    let c = Cleanup::new();
    let (log, bin) = lane_env(&c);
    let r = c.mk_lane_repo("r17", true);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/trivial"], &[("LANE_INSTALL_LOG", &log), ("LANE_INSTALLED_BIN", &bin)]);
    assert!(run.ok && run.has("no recorded build sha: rebuilding the lane binaries"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "ran\n");
    assert_eq!(std::fs::read_to_string(&bin).unwrap(), "NEW\n");
    // #834 (Codex re-run): `flow/lane-install.sh` records the sha it built
    // from on every successful install, so a later run with no pull of its
    // own can still tell whether the binaries are current.
    let build_sha_file = c.home().join(".local/state/lane/build-sha");
    assert_eq!(std::fs::read_to_string(&build_sha_file).unwrap().trim(), c.rev(&r, "main"));
}

/// #834 (Codex re-run): a missing record is untrusted, not a green light —
/// it rebuilds even when the pull that just ran did not touch flow/lane, the
/// same as when it did. `flow/lane-install.sh` now always writes the record
/// on success, so this is the recovery path for whatever ran before that
/// existed (a plain install, a lost or corrupted file).
#[test]
fn no_recorded_build_sha_rebuilds_even_when_the_pull_did_not_touch_the_crate() {
    let c = Cleanup::new();
    let (log, bin) = lane_env(&c);
    let r = c.mk_lane_repo("r18", false);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/trivial"], &[("LANE_INSTALL_LOG", &log), ("LANE_INSTALLED_BIN", &bin)]);
    assert!(run.ok && run.has("no recorded build sha: rebuilding the lane binaries"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "ran\n");
    assert_eq!(std::fs::read_to_string(&bin).unwrap(), "NEW\n");
    assert_eq!(c.rev(&r, "main"), c.rev(&r, "origin/main"));
}

/// #834 (Codex re-run): the exact reported failure shape — no record at all
/// (a plain lane-install ran before it existed), and main is already at the
/// tip when this run starts, so this run's own `git pull --ff-only` moves
/// nothing. The old old_head/new_head check read that as "nothing to do";
/// a missing record must rebuild anyway.
#[test]
fn no_recorded_build_sha_rebuilds_even_when_this_runs_pull_moves_nothing() {
    let c = Cleanup::new();
    let (log, bin) = lane_env(&c);
    let r = c.mk_lane_repo("r23", true);
    // Simulate main already advanced by another process before this run
    // starts, so this run's own `git pull --ff-only` is a no-op.
    c.git_ok(&["-C", r.to_str().unwrap(), "merge", "-q", "--ff-only", "origin/main"]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/trivial"], &[("LANE_INSTALL_LOG", &log), ("LANE_INSTALLED_BIN", &bin)]);
    assert!(run.ok && run.has("no recorded build sha: rebuilding the lane binaries"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "ran\n");
    assert_eq!(std::fs::read_to_string(&bin).unwrap(), "NEW\n");
}

#[test]
fn a_failed_rebuild_reports_the_error_keeps_the_old_binary_and_does_not_fail() {
    let c = Cleanup::new();
    let (log, bin) = lane_env(&c);
    let r = c.mk_lane_repo("r19", true);
    let env = [("LANE_INSTALL_LOG", log.as_str()), ("LANE_INSTALLED_BIN", bin.as_str()), ("LANE_INSTALL_FAIL", "1")];
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/trivial"], &env);
    assert!(run.ok, "{}", run.text());
    assert!(run.stderr.contains("merge-cleanup: lane rebuild failed, keeping the installed binaries:\ncompile error: boom"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&bin).unwrap(), "OLD\n");
    assert_eq!(c.rev(&r, "main"), c.rev(&r, "origin/main"));
}

#[test]
fn a_dry_run_never_rebuilds() {
    let c = Cleanup::new();
    let (log, bin) = lane_env(&c);
    let r = c.mk_lane_repo("r20", true);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/trivial", "--dry-run"], &[("LANE_INSTALL_LOG", &log), ("LANE_INSTALLED_BIN", &bin)]);
    assert!(run.ok && !run.has("rebuilding"), "{}", run.text());
    // #834: the dry-run guard sits after the fast-forward's own `step` call,
    // so a dry run still says what it would have pulled.
    assert!(run.has("would fast-forwarding main in"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "");
}

/// #834: a recorded build sha older than the tip rebuilds even when this
/// run's own pull is a no-op (main already at the tip when this run starts).
#[test]
fn a_stale_recorded_build_sha_rebuilds_even_when_this_runs_pull_moves_nothing() {
    let c = Cleanup::new();
    let (log, bin) = lane_env(&c);
    let r = c.mk_lane_repo("r21", true);
    let stale = c.rev(&r, "main");
    // Simulate main already advanced by another process before this run
    // starts, so this run's own `git pull --ff-only` is a no-op.
    c.git_ok(&["-C", r.to_str().unwrap(), "merge", "-q", "--ff-only", "origin/main"]);
    let build_sha_file = c.home().join(".local/state/lane/build-sha");
    std::fs::create_dir_all(build_sha_file.parent().unwrap()).unwrap();
    std::fs::write(&build_sha_file, format!("{stale}\n")).unwrap();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/trivial"], &[("LANE_INSTALL_LOG", &log), ("LANE_INSTALLED_BIN", &bin)]);
    assert!(run.ok && run.has("flow/lane changed: rebuilding the lane binaries"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "ran\n");
    assert_eq!(std::fs::read_to_string(&bin).unwrap(), "NEW\n");
    assert_eq!(std::fs::read_to_string(&build_sha_file).unwrap().trim(), c.rev(&r, "main"));
}

/// #834: the mirror case — even when *this run's own* pull moves HEAD onto a
/// commit touching flow/lane (which the old old_head-vs-new_head check alone
/// would read as "rebuild"), a build sha already recorded at that same tip
/// says the binaries are already current and must still skip.
#[test]
fn a_recorded_build_sha_already_at_the_tip_skips_even_when_this_runs_pull_moves_head() {
    let c = Cleanup::new();
    let (log, bin) = lane_env(&c);
    let r = c.mk_lane_repo("r22", true);
    let tip = c.rev(&r, "origin/main");
    let build_sha_file = c.home().join(".local/state/lane/build-sha");
    std::fs::create_dir_all(build_sha_file.parent().unwrap()).unwrap();
    std::fs::write(&build_sha_file, format!("{tip}\n")).unwrap();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/trivial"], &[("LANE_INSTALL_LOG", &log), ("LANE_INSTALLED_BIN", &bin)]);
    assert!(run.ok && !run.has("rebuilding"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "");
    assert_eq!(std::fs::read_to_string(&bin).unwrap(), "OLD\n");
    assert_eq!(c.rev(&r, "main"), tip);
}

// --- #736: uncommitted files in the worktree ---------------------------------

/// A modified tracked file, or an untracked one, in the workspace.
fn dirty(wt: &std::path::Path, kind: &str) {
    match kind {
        "modified" => std::fs::write(wt.join("f"), "changed\n").unwrap(),
        "untracked" => std::fs::write(wt.join("notes"), "unsaved\n").unwrap(),
        other => panic!("no such kind of dirty file: {other}"),
    }
}

#[test]
fn a_worktree_with_a_modified_or_untracked_file_is_refused_naming_it() {
    // An idle herdr agent sits in the worktree: the refusal comes before the
    // live-session guard would close its pane. `status.showUntrackedFiles=no`
    // hides untracked files from a bare `git status`, but not from the guard.
    for (kind, name, hide_untracked) in [("modified", "f", false), ("untracked", "notes", false), ("untracked", "notes", true)] {
        let c = Cleanup::new();
        let (r, wt) = lane_workspace(&c, "r23", "implement-23");
        if hide_untracked {
            c.git_ok(&["-C", s(&r), "config", "status.showUntrackedFiles", "no"]);
        }
        dirty(&wt, kind);
        c.set_agents(&format!(r#"[{{"name":"skills-23","pane_id":"w23:p1","cwd":"{}","agent_status":"idle"}}]"#, wt.display()));
        c.clear_calls();
        let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
        let want = format!("merge-cleanup: refusing to remove {} — 1 {kind} file(s) would be lost: {name} (--discard overrides)", wt.display());
        assert!(!run.ok && run.stderr.contains(&want), "{kind} {hide_untracked}: {}", run.text());
        assert!(wt.join(name).is_file() && c.has_branch(&r, "caneff/merged-one"), "{kind}: {}", run.text());
        assert!(!c.calls().contains("pane close"), "{kind}: {}", c.calls());
    }
}

#[test]
fn a_worktree_git_cannot_read_is_never_removed() {
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let other = root.join("other");
    let wt = other.join(".claude/worktrees/implement-9");
    // A corrupt index: `git status` fails, `git worktree remove --force` would not.
    std::fs::write(other.join(".git/worktrees/implement-9/index"), "junk\n").unwrap();
    let run = c.mc(Tools::Full, &["--repo", s(&other), "caneff/merged-one"], &[]);
    let want = format!("merge-cleanup: refusing to remove {} — git status failed there", wt.display());
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root), "--yes"], &[]);
    assert!(run.has("  other caneff/merged-one  0 commits past PR #7  worktree: git status failed (unreadable, not removed)"), "{}", run.text());
    assert!(run.has("  other  caneff/merged-one  unreadable, not removed  0 commits past PR #7"), "{}", run.text());
    assert!(wt.is_dir() && c.has_branch(&other, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn force_alone_still_refuses_a_dirty_worktree_and_discard_removes_it() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r24", "implement-24");
    dirty(&wt, "modified");
    dirty(&wt, "untracked");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--force"], &[]);
    assert!(!run.ok && run.stderr.contains("1 modified, 1 untracked file(s) would be lost: f, notes"), "{}", run.text());
    assert!(wt.join("notes").is_file() && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--discard"], &[]);
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
    assert!(run.has(&format!("--discard: {} — 1 modified, 1 untracked file(s) would be lost: f, notes", wt.display())), "{}", run.text());
}

// --- #801: an ignored entry that is not a cache is work too -----------------

/// Ignore `names` through the repo's `.git/info/exclude` and create each as a
/// directory holding one file in `wt`.
fn ignored_dirs(r: &std::path::Path, wt: &std::path::Path, names: &[&str]) {
    let exclude: String = names.iter().map(|n| format!("{n}/\n")).collect();
    std::fs::write(r.join(".git/info/exclude"), exclude).unwrap();
    for n in names {
        std::fs::create_dir_all(wt.join(n)).unwrap();
        std::fs::write(wt.join(n).join("x"), "x\n").unwrap();
    }
}

#[test]
fn a_worktree_holding_scratch_is_refused_naming_it() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r26", "implement-26");
    ignored_dirs(&r, &wt, &[".scratch", "node_modules"]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    let want = format!("merge-cleanup: refusing to remove {} — 1 ignored file(s) would be lost: .scratch/x (--discard overrides)", wt.display());
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    assert!(wt.join(".scratch/x").is_file() && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--dry-run"], &[]);
    assert!(!run.ok && run.stderr.contains(&want) && !run.has("would remove"), "{}", run.text());
    assert!(wt.join(".scratch/x").is_file() && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--discard"], &[]);
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
    assert!(run.has(&format!("--discard: {} — 1 ignored file(s) would be lost: .scratch/x", wt.display())), "{}", run.text());
}

#[test]
fn a_worktree_holding_only_caches_is_removed_and_they_are_listed() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r27", "implement-27");
    // A cache nested under a directory holding nothing else still counts.
    ignored_dirs(&r, &wt, &["node_modules", "sub/__pycache__", "target", ".venv", ".pytest_cache", ".ruff_cache", ".mypy_cache"]);
    let names = ".mypy_cache/, .pytest_cache/, .ruff_cache/, .venv/, node_modules/ and 2 more";
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--dry-run"], &[]);
    let want = format!("would discard 7 cache file(s) in {}: {names}", wt.display());
    assert!(run.ok && run.has(&want) && wt.join("target/x").is_file(), "{}", run.text());
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
    assert!(run.has(&format!("discarding 7 cache file(s) in {}: {names}", wt.display())), "{}", run.text());
}

#[test]
fn caches_git_lists_by_their_contents_or_as_a_symlink_are_still_caches() {
    // pytest writes `*` into its own .gitignore, so git lists what is inside
    // `.pytest_cache/`; a symlinked `node_modules` is listed with no
    // trailing slash.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r28", "implement-28");
    std::fs::write(r.join(".git/info/exclude"), "node_modules\n").unwrap();
    std::fs::create_dir_all(wt.join(".pytest_cache/v")).unwrap();
    std::fs::write(wt.join(".pytest_cache/.gitignore"), "*\n").unwrap();
    std::fs::write(wt.join(".pytest_cache/v/x"), "x\n").unwrap();
    std::os::unix::fs::symlink(c.root(), wt.join("node_modules")).unwrap();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
    assert!(run.has(&format!("discarding 3 cache file(s) in {}:", wt.display())), "{}", run.text());
}

#[test]
fn an_ignored_file_under_a_folder_merely_named_like_a_cache_is_refused() {
    // Deny by default: `target/` here is neither ignored itself nor marked
    // fully ignored by its own .gitignore, so `run.log` is work.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r30", "implement-30");
    std::fs::write(r.join(".git/info/exclude"), "*.log\n").unwrap();
    std::fs::create_dir_all(wt.join("notes/target")).unwrap();
    std::fs::write(wt.join("notes/target/run.log"), "evidence\n").unwrap();
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    let want = format!("merge-cleanup: refusing to remove {} — 1 ignored file(s) would be lost: notes/target/run.log (--discard overrides)", wt.display());
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    assert!(wt.join("notes/target/run.log").is_file(), "{}", run.text());
}

#[test]
fn scratch_alongside_many_caches_is_never_elided_behind_the_cache_count() {
    // #823: the two counts used to share the "ignored file(s)" label, so a
    // reader could not tell whether `.scratch/` sat in the small non-cache
    // list or the long cache list's own "and N more" tail. They're printed
    // as two distinctly labelled lines, non-cache first, so `.scratch/`
    // always appears by name regardless of how many caches follow it.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r31", "implement-31");
    ignored_dirs(&r, &wt, &[".scratch", "node_modules", "target", ".venv", ".pytest_cache", ".ruff_cache", ".mypy_cache"]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--discard"], &[]);
    assert!(run.ok && !wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
    let dirty_line_idx = run.stdout.lines().position(|l| l.contains("--discard:") && l.contains("1 ignored file(s) would be lost: .scratch/x"));
    let cache_line_idx = run.stdout.lines().position(|l| l.contains("discarding 6 cache file(s)"));
    assert!(dirty_line_idx.is_some() && cache_line_idx.is_some() && dirty_line_idx < cache_line_idx, "{}", run.text());
}

#[test]
fn scratch_is_never_elided_behind_bulk_modified_and_untracked_names() {
    // #838: dirty_text's own name list chained modified, untracked, then
    // ignored, so 5+ modified/untracked names filled first_names' NAMES_SHOWN
    // and .scratch/ (the scarcest, least-recoverable class) fell into "and N
    // more" with nothing else naming it. Ignored goes first in the chain, so
    // it always shows regardless of how many modified/untracked names follow.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r32", "implement-32");
    ignored_dirs(&r, &wt, &[".scratch"]);
    dirty(&wt, "modified"); // "f", already tracked in the fixture
    for name in ["a", "b", "c", "d"] {
        std::fs::write(wt.join(name), "unsaved\n").unwrap();
    }
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    let want = format!(
        "merge-cleanup: refusing to remove {} — 1 modified, 4 untracked, 1 ignored file(s) would be lost: .scratch/x, f, a, b, c, d (--discard overrides)",
        wt.display()
    );
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
}

#[test]
fn six_or_more_ignored_names_are_all_shown_none_elided() {
    // Codex adversarial review on PR #847: dirty_text still fed every ignored
    // name into the same NAMES_SHOWN-capped list, so six or more non-cache
    // ignored entries could still push one — .scratch/ included — into "and N
    // more". Non-cache ignored is exactly what --discard destroys unseen, so
    // none of it may be capped; only modified/untracked names are.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r33", "implement-33");
    ignored_dirs(&r, &wt, &[".scratch", "z1", "z2", "z3", "z4", "z5"]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    let want = format!(
        "merge-cleanup: refusing to remove {} — 6 ignored file(s) would be lost: .scratch/x, z1/x, z2/x, z3/x, z4/x, z5/x (--discard overrides)",
        wt.display()
    );
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
}

#[test]
fn an_empty_ignored_directory_is_removed_and_named() {
    // #869/#946, reversing #823: `--ignored=matching` collapses an ignored
    // directory to one entry whatever it holds, so an empty one read as "1
    // ignored file(s)" and forced a needless --discard through Chris's hands
    // — six times running in twitch-rules-scroller on 2026-09-16. Nothing is
    // lost, so it no longer refuses; the run still names what it took, so the
    // output stays a full account of what cleanup touched.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r32", "implement-32");
    std::fs::write(r.join(".git/info/exclude"), ".scratch/\n").unwrap();
    std::fs::create_dir(wt.join(".scratch")).unwrap();
    let at = wt.join(".scratch");

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--dry-run"], &[]);
    assert!(run.ok && run.has(&format!("would remove the empty ignored directory at {}", at.display())), "{}", run.text());
    assert!(at.is_dir() && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && run.has(&format!("removing the empty ignored directory at {}", at.display())), "{}", run.text());
    assert!(!wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn an_ignored_directory_of_only_empty_subdirectories_is_empty_too() {
    // "Zero files" means nowhere beneath it, not just at the top: a walk that
    // stopped at the first directory entry would call this one work.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r34", "implement-34");
    std::fs::write(r.join(".git/info/exclude"), "e2e-artifacts/\n").unwrap();
    std::fs::create_dir_all(wt.join("e2e-artifacts/shots/full")).unwrap();
    let at = wt.join("e2e-artifacts");

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && run.has(&format!("removing the empty ignored directory at {}", at.display())), "{}", run.text());
    assert!(!wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn a_full_ignored_directory_refuses_with_its_real_count_and_names() {
    // The dangerous direction of #946: one collapsed entry read as "1 ignored
    // file(s) would be lost" however much it held, so --discard was approved
    // against a count that understated the loss. The refusal now states every
    // file, at any depth.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r35", "implement-35");
    std::fs::write(r.join(".git/info/exclude"), "e2e-artifacts/\n").unwrap();
    std::fs::create_dir_all(wt.join("e2e-artifacts/shots")).unwrap();
    for f in ["e2e-artifacts/a.png", "e2e-artifacts/c.png", "e2e-artifacts/shots/b.png"] {
        std::fs::write(wt.join(f), "x\n").unwrap();
    }
    let want = format!(
        "merge-cleanup: refusing to remove {} — 3 ignored file(s) would be lost: e2e-artifacts/a.png, e2e-artifacts/c.png, e2e-artifacts/shots/b.png (--discard overrides)",
        wt.display()
    );
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    assert!(wt.join("e2e-artifacts/a.png").is_file() && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn an_unreadable_ignored_directory_still_refuses() {
    // Fail closed (#801): a walk that cannot read the directory says nothing
    // about what is in it, and an io::Error read as "nothing in there" would
    // approve a destructive removal on a permission error.
    use std::os::unix::fs::PermissionsExt;
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r36", "implement-36");
    std::fs::write(r.join(".git/info/exclude"), "e2e-artifacts/\n").unwrap();
    let at = wt.join("e2e-artifacts");
    std::fs::create_dir(&at).unwrap();
    std::fs::write(at.join("shot.png"), "x\n").unwrap();
    std::fs::set_permissions(&at, std::fs::Permissions::from_mode(0o000)).unwrap();
    if std::fs::read_dir(&at).is_ok() {
        // Root, or a filesystem that ignores modes: the directory is still
        // readable, so this run would witness nothing. Say so rather than
        // fail, and leave the tree as found.
        std::fs::set_permissions(&at, std::fs::Permissions::from_mode(0o755)).unwrap();
        eprintln!("skipped: chmod 000 did not make the directory unreadable here");
        return;
    }

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    std::fs::set_permissions(&at, std::fs::Permissions::from_mode(0o755)).unwrap();
    let want = format!("merge-cleanup: refusing to remove {} — 1 ignored file(s) would be lost: e2e-artifacts/ (--discard overrides)", wt.display());
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
    assert!(at.join("shot.png").is_file() && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn a_quoted_ignored_directory_is_classified_by_its_contents_too() {
    // Correctness axis C1 on the round-1 diff: git quotes a porcelain path
    // holding a non-ASCII byte (`core.quotePath`), and the quoted form ends
    // with `"`, not `/`. Matching on the slash filed `café/` as a plain file
    // and never walked it, so both bugs survived intact for such a name — the
    // empty one still forced a --discard, and a full one still claimed "1
    // ignored file(s)" whatever it held.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r37", "implement-37");
    std::fs::write(r.join(".git/info/exclude"), "café/\n").unwrap();
    std::fs::create_dir(wt.join("café")).unwrap();
    for f in ["a.png", "b.png"] {
        std::fs::write(wt.join("café").join(f), "x\n").unwrap();
    }
    let want = format!(
        "merge-cleanup: refusing to remove {} — 2 ignored file(s) would be lost: café/a.png, café/b.png (--discard overrides)",
        wt.display()
    );
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());

    // The same name, emptied: nothing to lose, so it is removed and named.
    for f in ["a.png", "b.png"] {
        std::fs::remove_file(wt.join("café").join(f)).unwrap();
    }
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && run.has(&format!("removing the empty ignored directory at {}", wt.join("café").display())), "{}", run.text());
    assert!(!wt.exists() && !c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn the_empty_directory_line_is_not_printed_when_nothing_is_removed() {
    // Correctness C2 / spec P1: the line was printed inside guard_files,
    // which runs before the live-session guard, so a worktree someone was
    // still working in announced a removal that never happened — the inverse
    // of the full account of what cleanup touched that the line exists for.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r38", "implement-38");
    std::fs::write(r.join(".git/info/exclude"), "e2e-artifacts/\n").unwrap();
    std::fs::create_dir(wt.join("e2e-artifacts")).unwrap();
    c.session("live", &format!(r#"{{"pid":{},"cwd":"{}","procStart":"{}"}}"#, me(), wt.display(), me_start()));

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.stderr.contains("a live session is in it"), "{}", run.text());
    assert!(!run.stdout.contains("the empty ignored directory"), "{}", run.text());
    assert!(wt.join("e2e-artifacts").is_dir() && c.has_branch(&r, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn a_quoted_rename_decodes_both_of_its_paths() {
    // Verification pass V1 on the C1 fix: porcelain v1 writes a rename as
    // `<orig> -> <new>` with each path quoted on its own, so decoding the
    // line as one path stripped the outer quotes and left the inner pair
    // stranded — `"a" -> "b"` read as `a" -> "b`. Only the displayed name was
    // affected, never a refusal, but a guard that exists to say what is about
    // to be destroyed has to name it correctly.
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r39", "implement-39");
    std::fs::write(wt.join("café.txt"), "x\n").unwrap();
    c.git_ok(&["-C", s(&wt), "add", "café.txt"]);
    c.git_ok(&["-C", s(&wt), "commit", "-qm", "add it"]);
    c.git_ok(&["-C", s(&wt), "mv", "café.txt", "naïve.txt"]);

    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one", "--force"], &[]);
    let want = format!(
        "merge-cleanup: refusing to remove {} — 1 modified file(s) would be lost: café.txt -> naïve.txt (--discard overrides)",
        wt.display()
    );
    assert!(!run.ok && run.stderr.contains(&want), "{}", run.text());
}

#[test]
fn a_sibling_holding_only_caches_is_not_listed_stale() {
    let c = Cleanup::new();
    let r = c.mkfixture("r29");
    let wts = r.join(".claude/worktrees");
    c.worktree_add(&r, &["--detach", s(&wts.join("agent-cached")), "origin/main"]);
    c.worktree_add(&r, &["--detach", s(&wts.join("agent-old")), "origin/main"]);
    ignored_dirs(&r, &wts.join("agent-cached"), &["target"]);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/ff-merged", "--dry-run"], &[]);
    assert!(run.ok, "{}", run.text());
    assert_eq!(run.stale(), vec![wts.join("agent-old").display().to_string()], "{}", run.text());
}

#[test]
fn a_sweep_with_yes_never_removes_a_worktree_holding_scratch() {
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let other = root.join("other");
    let wt = other.join(".claude/worktrees/implement-9");
    ignored_dirs(&other, &wt, &[".scratch", "node_modules"]);
    let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root), "--yes"], &[]);
    let held = "  other caneff/merged-one  0 commits past PR #7  worktree: 0 modified, 0 untracked, 1 ignored, 1 cache (dirty, not removed)";
    assert!(run.ok && run.stdout.lines().any(|l| l == held), "{}", run.text());
    assert!(run.has("  other  caneff/merged-one  dirty, not removed  0 commits past PR #7"), "{}", run.text());
    assert!(wt.join(".scratch/x").is_file() && c.has_branch(&other, "caneff/merged-one"), "{}", run.text());
}

#[test]
fn a_sweep_never_removes_a_dirty_worktree_and_cleans_the_clean_ones() {
    // The dirty worktree holds caneff/ff-merged, which sorts before the clean
    // caneff/merged-one: the sweep goes on past a held row.
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let other = root.join("other");
    let wt = other.join(".claude/worktrees/implement-ff");
    c.worktree_add(&other, &[s(&wt), "caneff/ff-merged"]);
    dirty(&wt, "untracked");
    let held = "  other caneff/ff-merged  0 commits past origin/main  worktree: 0 modified, 1 untracked, 0 ignored, 0 cache (dirty, not removed)";
    let clean = "  other caneff/merged-one  0 commits past PR #7  worktree: 0 modified, 0 untracked, 0 ignored, 0 cache";
    for flag in ["--dry-run", "--yes"] {
        let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root), flag, "--discard"], &[]);
        assert!(!run.ok && run.stderr.contains("merge-cleanup: --discard takes one branch, not --sweep"), "{}", run.text());
    }
    let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root), "--dry-run"], &[]);
    assert!(run.ok && run.stdout.lines().any(|l| l == held) && run.stdout.lines().any(|l| l == clean), "{}", run.stdout);

    let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root), "--yes"], &[]);
    assert!(run.ok && run.stdout.lines().any(|l| l == held), "{}", run.text());
    let rows: Vec<&str> = run.stdout.lines().skip_while(|l| *l != "sweep summary").skip(1).take_while(|l| l.starts_with("  ")).collect();
    assert!(rows.contains(&"  other  caneff/ff-merged   dirty, not removed  0 commits past origin/main"), "{rows:#?}");
    assert!(rows.contains(&"  other  caneff/merged-one  cleaned             0 commits past PR #7"), "{rows:#?}");
    assert!(wt.join("notes").is_file() && c.has_branch(&other, "caneff/ff-merged"), "{}", run.text());
    assert!(!c.has_branch(&other, "caneff/merged-one") && !other.join(".claude/worktrees/implement-9").exists(), "{}", run.text());
}

// --- #735: a repo with no .claude/worktrees lists nothing ---------------------

#[test]
fn a_repo_with_no_worktrees_dir_adds_no_stale_line() {
    let c = Cleanup::new();
    let root = sweep_root(&c);
    assert!(!root.join("noremote/.claude").exists());
    let run = c.mc(Tools::Full, &["--sweep", "--root", s(&root), "--dry-run"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!run.has("*"), "{}", run.text());
    assert_eq!(run.stale(), vec![root.join("other/.claude/worktrees/agent-old").display().to_string()], "{}", run.text());

    let r = c.mkfixture("plain");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok && !run.has("stale, not removed"), "{}", run.text());
}

// --- #746: the stale report decides a worker's own session like the guard ----

#[test]
fn a_sibling_whose_only_live_signal_is_an_idle_workers_own_session_is_stale() {
    for (status, stale) in [("idle", true), ("working", false)] {
        let c = Cleanup::new();
        let r = c.mkfixture("r21");
        let wts = r.join(".claude/worktrees");
        let sibling = wts.join("implement-done");
        c.worktree_add(&r, &["--detach", s(&sibling), "origin/main"]);
        c.session("worker", &format!(r#"{{"pid":{},"cwd":"{}","sessionId":"sess-21"}}"#, me(), sibling.display()));
        c.set_agents(&format!(
            r#"[{{"name":"skills-21","pane_id":"w21:p1","cwd":"{}","agent_status":"{status}","agent_session":{{"value":"sess-21"}}}}]"#,
            sibling.display()
        ));
        let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/ff-merged", "--dry-run"], &[]);
        assert!(run.ok, "{}", run.text());
        let want: Vec<String> = if stale { vec![sibling.display().to_string()] } else { vec![] };
        assert_eq!(run.stale(), want, "{status}: {}", run.text());
        assert!(sibling.is_dir() && !c.calls().contains("pane close"), "{}", c.calls());
    }
}

// --- #758: a closed stdout stops the run instead of panicking ----------------

#[test]
fn a_reader_that_closes_early_gets_a_clean_nonzero_exit_no_panic_text() {
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let (code, stderr) = c.mc_broken_pipe(Tools::Full, &["--sweep", "--root", s(&root), "--dry-run"]);
    assert_eq!(code, Some(lane::io_safe::BROKEN_PIPE_EXIT), "stderr: {stderr}");
    assert!(!stderr.contains("panicked"), "{stderr}");
    assert!(!stderr.contains("Broken pipe"), "{stderr}");
}

// --- #876: --reap, the scoped reaper -----------------------------------------

/// A repo whose `.claude/worktrees/implement-<n>` workspaces hold merged
/// `implement-<n>` branches — what the reaper is pointed at.
fn reap_repo(c: &Cleanup, rel: &str, ns: &[&str]) -> std::path::PathBuf {
    let r = c.mkfixture(rel);
    for n in ns {
        c.mk_implement_branch(&r, n);
        let b = format!("implement-{n}");
        c.worktree_add(&r, &[s(&r.join(".claude/worktrees").join(&b)), &b]);
    }
    r
}

#[test]
fn reap_without_yes_lists_each_workspace_and_removes_nothing() {
    let c = Cleanup::new();
    let r = reap_repo(&c, "r30", &["101"]);
    let wt = r.join(".claude/worktrees/implement-101");
    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r)], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(run.has(&format!("  {}  would reap", wt.display())), "{}", run.text());
    assert!(run.has("reap summary: 1 would be reaped, 0 skipped (dry run; --yes removes)"), "{}", run.text());
    assert!(wt.is_dir() && c.has_branch(&r, "implement-101"), "{}", run.text());
}

#[test]
fn reap_with_yes_removes_the_landed_workspace_and_leaves_the_rest() {
    let c = Cleanup::new();
    let r = reap_repo(&c, "r31", &["101", "102"]);
    let (landed, kept) = (r.join(".claude/worktrees/implement-101"), r.join(".claude/worktrees/implement-102"));
    // implement-102 kept going past the sha its merged PR covers.
    std::fs::write(kept.join("f"), "one\nmore\n").unwrap();
    c.git_ok(&["-C", s(&kept), "commit", "-qam", "past the PR"]);
    let tip = c.rev(&r, "implement-101");
    let short = c.git_out(&["-C", s(&r), "rev-parse", "--short", &tip]);

    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!landed.exists() && !c.has_branch(&r, "implement-101"), "{}", run.text());
    assert_eq!(c.git_out(&["-C", s(&r), "ls-remote", "--heads", "origin", "implement-101"]), "", "{}", run.text());
    assert_eq!(c.rev(&r, &format!("refs/deleted/implement-101@{short}")), tip);
    assert!(kept.is_dir() && c.has_branch(&r, "implement-102"), "{}", run.text());
    assert!(run.has(&format!("  {}  reaped", landed.display())), "{}", run.text());
    assert!(run.has(&format!("  {}  not merged, not removed", kept.display())), "{}", run.text());
    assert!(run.has("reap summary: 1 reaped, 1 skipped"), "{}", run.text());
}

#[test]
fn reap_skips_a_workspace_holding_work_and_names_the_files() {
    let c = Cleanup::new();
    let r = reap_repo(&c, "r32", &["103"]);
    let wt = r.join(".claude/worktrees/implement-103");
    std::fs::write(wt.join("notes"), "unsaved\n").unwrap();
    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    let want = format!("  {}  dirty, not removed: 1 untracked file(s) would be lost: notes", wt.display());
    assert!(run.has(&want), "{}", run.text());
    assert!(wt.is_dir() && c.has_branch(&r, "implement-103"), "{}", run.text());
    assert!(run.has("reap summary: 0 reaped, 1 skipped"), "{}", run.text());
}

#[test]
fn reap_skips_a_workspace_with_a_live_session_and_names_it() {
    for who in ["registry", "herdr"] {
        let c = Cleanup::new();
        let r = reap_repo(&c, "r33", &["104"]);
        let wt = r.join(".claude/worktrees/implement-104");
        let want = match who {
            "registry" => {
                c.session("live", &format!(r#"{{"pid":{},"cwd":"{}","procStart":"{}"}}"#, me(), wt.display(), me_start()));
                format!("live session, not removed: pid {}", me())
            }
            _ => {
                c.set_agents(&format!(
                    r#"[{{"name":"skills-33","pane_id":"w33:p1","cwd":"{}","agent_status":"working"}}]"#,
                    wt.display()
                ));
                "live session, not removed: herdr agent skills-33 (w33:p1)".to_string()
            }
        };
        let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
        assert!(run.ok, "{who}: {}", run.text());
        assert!(run.has(&format!("  {}  {want}", wt.display())), "{who}: {}", run.text());
        assert!(wt.is_dir() && c.has_branch(&r, "implement-104"), "{who}: {}", run.text());
        assert!(!c.calls().contains("pane close"), "{who}: {}", c.calls());
    }
}

#[test]
fn reap_considers_only_this_repos_implement_workspaces() {
    let c = Cleanup::new();
    let r = reap_repo(&c, "r34", &["105"]);
    let other = reap_repo(&c, "r35", &["109"]);
    let wts = r.join(".claude/worktrees");
    // Landed, clean and dead like implement-105, and every one of them out
    // of the reaper's reach: a branch that is not implement-*, a workspace
    // outside .claude/worktrees/, one under a directory that merely starts
    // with that path, and another repo's workspace.
    c.worktree_add(&r, &[s(&wts.join("agent-old")), "caneff/merged-one"]);
    for (n, at) in [("107", r.join("elsewhere/implement-107")), ("108", r.join(".claude/worktrees-evil/implement-108"))] {
        c.mk_implement_branch(&r, n);
        c.worktree_add(&r, &[s(&at), &format!("implement-{n}")]);
    }

    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(run.has("reap plan: 1 implement-* workspace(s) under"), "{}", run.text());
    assert!(!c.has_branch(&r, "implement-105"), "{}", run.text());
    for at in [
        wts.join("agent-old"),
        r.join("elsewhere/implement-107"),
        r.join(".claude/worktrees-evil/implement-108"),
        other.join(".claude/worktrees/implement-109"),
    ] {
        assert!(at.is_dir(), "{} was removed:\n{}", at.display(), run.text());
        assert!(!run.has(&at.display().to_string()), "{} was listed:\n{}", at.display(), run.text());
    }
    assert!(c.has_branch(&r, "caneff/merged-one") && c.has_branch(&r, "implement-107"), "{}", run.text());
    assert!(c.has_branch(&r, "implement-108") && c.has_branch(&other, "implement-109"), "{}", run.text());
}

#[test]
fn reap_refuses_every_flag_that_would_let_it_override_a_guard() {
    let c = Cleanup::new();
    let r = reap_repo(&c, "r36", &["110"]);
    let wt = r.join(".claude/worktrees/implement-110");
    let cases: &[(&[&str], &str)] = &[
        (&["--reap", "--repo", s(&r), "implement-110"], "merge-cleanup: --reap takes no branch or PR"),
        (&["--reap", "--repo", s(&r), "7"], "merge-cleanup: --reap takes no branch or PR"),
        (&["--reap", "--repo", s(&r), "--yes", "--discard"], "merge-cleanup: --discard takes one branch, not --reap"),
        (&["--reap", "--repo", s(&r), "--yes", "--force"], "merge-cleanup: --force takes one branch, not --reap"),
        (&["--reap", "--sweep"], "merge-cleanup: --reap and --sweep are different forms"),
        (&["--reap", "--repo", s(&r), "--root", "/x"], "merge-cleanup: --root takes --sweep, not --reap"),
    ];
    for (args, want) in cases {
        let run = c.mc(Tools::Full, args, &[]);
        assert!(!run.ok && run.stderr.trim_end() == *want, "{args:?}: {}", run.text());
        assert!(wt.is_dir() && c.has_branch(&r, "implement-110"), "{args:?}: {}", run.text());
    }
}

#[test]
fn reap_with_both_dry_run_and_yes_removes_nothing() {
    let c = Cleanup::new();
    let r = reap_repo(&c, "r37", &["111"]);
    let wt = r.join(".claude/worktrees/implement-111");
    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes", "--dry-run"], &[]);
    assert!(run.ok && run.has("reap plan (dry run):"), "{}", run.text());
    assert!(wt.is_dir() && c.has_branch(&r, "implement-111"), "{}", run.text());
}

#[test]
fn reap_on_a_repo_with_no_implement_workspaces_says_so() {
    let c = Cleanup::new();
    let r = c.mkfixture("r38");
    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r)], &[]);
    let want = format!("nothing to reap under {}", r.join(".claude/worktrees").display());
    assert!(run.ok && run.has(&want), "{}", run.text());
}

/// #875: every claim here is one a test above holds the behaviour to — the
/// dry-run default (`reap_without_yes_...`), what --yes then does
/// (`reap_with_yes_...`), the missing overrides
/// (`reap_refuses_every_flag_...`) and the reach
/// (`reap_considers_only_this_repos_...`).
#[test]
fn help_describes_reap_as_dry_run_by_default_and_unable_to_discard() {
    let c = Cleanup::new();
    let run = c.mc(Tools::Full, &["--help"], &[]);
    assert!(run.ok);
    assert!(run.stdout.contains("  merge-cleanup --reap [--repo <path>] [--yes] [--dry-run]\n"), "{}", run.stdout);
    assert!(run.stdout.contains("--reap cleans up one repo's own implement-* workspaces"), "{}", run.stdout);
    assert!(run.stdout.contains("dry run by default: it removes nothing without --yes"), "{}", run.stdout);
    assert!(run.stdout.contains("no --discard and no --force"), "{}", run.stdout);
    assert!(run.stdout.contains("this run's own directory is in is skipped"), "{}", run.stdout);
}

#[test]
fn reap_run_from_inside_a_workspace_never_deletes_the_ground_it_stands_on() {
    // The correctness axis on PR #876: with no --repo the repo is the cwd,
    // and a run started inside a workspace listed itself, removed the
    // directory it was standing in, and then reported nonsense about every
    // workspace after it.
    let c = Cleanup::new();
    let r = reap_repo(&c, "r39", &["112", "113"]);
    let (here, next) = (r.join(".claude/worktrees/implement-112"), r.join(".claude/worktrees/implement-113"));
    let tip = c.rev(&r, "implement-113");
    let short = c.git_out(&["-C", s(&r), "rev-parse", "--short", &tip]);

    let run = c.mc_in(Tools::Full, &here, &["--reap", "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(here.is_dir() && c.has_branch(&r, "implement-112"), "{}", run.text());
    assert!(run.has(&format!("  {}  this run's own directory, not removed", here.display())), "{}", run.text());
    assert!(!next.exists() && !c.has_branch(&r, "implement-113"), "{}", run.text());
    assert_eq!(c.git_out(&["-C", s(&r), "ls-remote", "--heads", "origin", "implement-113"]), "", "{}", run.text());
    assert_eq!(c.rev(&r, &format!("refs/deleted/implement-113@{short}")), tip, "{}", run.text());
    assert!(run.has("reap summary: 1 reaped, 1 skipped"), "{}", run.text());
}

#[test]
fn a_workspace_that_goes_dirty_between_the_plan_and_the_removal_is_refused_not_failed() {
    // The spec axis on PR #876: pass 2 re-runs the guards, and a guard that
    // refuses there is an answer — "skipped and named", exit 0 — not a
    // failure of the run. A pre-push hook fired by the first workspace's own
    // cleanup drops a file in the second one, which is the race in the small.
    let c = Cleanup::new();
    let r = reap_repo(&c, "r40", &["114", "115"]);
    let (first, second) = (r.join(".claude/worktrees/implement-114"), r.join(".claude/worktrees/implement-115"));
    let hook = r.join(".git/hooks/pre-push");
    std::fs::write(&hook, format!("#!/bin/sh\necho unsaved > {}/notes\n", second.display())).unwrap();
    std::fs::set_permissions(&hook, std::os::unix::fs::PermissionsExt::from_mode(0o755)).unwrap();

    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!first.exists() && !c.has_branch(&r, "implement-114"), "{}", run.text());
    let want = format!("  {}  dirty, not removed: 1 untracked file(s) would be lost: notes (refused at removal)", second.display());
    assert!(run.has(&want), "{}", run.text());
    assert!(second.is_dir() && c.has_branch(&r, "implement-115"), "{}", run.text());
    assert!(run.has("reap summary: 1 reaped, 1 skipped"), "{}", run.text());
}

#[test]
fn reap_pointed_at_a_workspace_still_cleans_up_every_workspace() {
    // --repo may name a linked worktree, which is itself a candidate. Every
    // git call anchors at the primary checkout, so removing that one does
    // not pull the ground out from under the workspaces after it.
    let c = Cleanup::new();
    let r = reap_repo(&c, "r41", &["116", "117"]);
    let wts = r.join(".claude/worktrees");
    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&wts.join("implement-116")), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    for n in ["116", "117"] {
        assert!(!wts.join(format!("implement-{n}")).exists(), "implement-{n}: {}", run.text());
        assert!(!c.has_branch(&r, &format!("implement-{n}")), "implement-{n}: {}", run.text());
        assert_eq!(c.git_out(&["-C", s(&r), "ls-remote", "--heads", "origin", &format!("implement-{n}")]), "", "{}", run.text());
    }
    assert_eq!(deleted_records(&c, &r).len(), 2, "{:?}", deleted_records(&c, &r));
    assert!(run.has("reap summary: 2 reaped, 0 skipped"), "{}", run.text());
}

#[test]
fn a_branch_that_moved_to_another_worktree_since_the_plan_is_refused() {
    // Codex pass on PR #878: the plan names a workspace, but the cleanup
    // re-resolves the branch for itself. A branch moved in between — here by
    // a pre-push hook the first workspace's own cleanup fires — would put a
    // worktree the plan never listed, outside .claude/worktrees/ at that,
    // in reach of the removal.
    let c = Cleanup::new();
    let r = reap_repo(&c, "r42", &["118", "119"]);
    let (first, planned) = (r.join(".claude/worktrees/implement-118"), r.join(".claude/worktrees/implement-119"));
    let moved_to = c.root().join("r42-elsewhere");
    let hook = r.join(".git/hooks/pre-push");
    std::fs::write(
        &hook,
        format!(
            "#!/bin/sh\nunset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE\n\
             git -C {repo} worktree remove --force {planned}\n\
             git -C {repo} worktree add -q {moved} implement-119\n",
            repo = r.display(),
            planned = planned.display(),
            moved = moved_to.display()
        ),
    )
    .unwrap();
    std::fs::set_permissions(&hook, std::os::unix::fs::PermissionsExt::from_mode(0o755)).unwrap();

    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!first.exists() && !c.has_branch(&r, "implement-118"), "{}", run.text());
    assert!(moved_to.is_dir() && c.has_branch(&r, "implement-119"), "the moved worktree was touched:\n{}", run.text());
    let want = format!("  {}  moved since the plan, not removed: {} now holds implement-119", planned.display(), moved_to.display());
    assert!(run.has(&want), "{}", run.text());
    assert!(run.has("reap summary: 1 reaped, 1 skipped"), "{}", run.text());
}

#[test]
fn a_branch_that_moved_into_the_primary_checkout_since_the_plan_is_refused() {
    // #881: the re-check used the linked-only lookup, so a primary checkout
    // holding the branch read as no holder and the cleanup switched it off
    // the branch and deleted the branch.
    let c = Cleanup::new();
    let r = reap_repo(&c, "r43", &["118", "119"]);
    let (first, planned) = (r.join(".claude/worktrees/implement-118"), r.join(".claude/worktrees/implement-119"));
    let hook = r.join(".git/hooks/pre-push");
    std::fs::write(
        &hook,
        format!(
            "#!/bin/sh\nunset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE\n\
             git -C {repo} worktree remove --force {planned}\n\
             git -C {repo} checkout -q implement-119\n",
            repo = r.display(),
            planned = planned.display(),
        ),
    )
    .unwrap();
    std::fs::set_permissions(&hook, std::os::unix::fs::PermissionsExt::from_mode(0o755)).unwrap();

    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!first.exists() && !c.has_branch(&r, "implement-118"), "{}", run.text());
    assert!(c.has_branch(&r, "implement-119"), "the branch the primary checkout holds was deleted:\n{}", run.text());
    let head = c.git_out(&["-C", s(&r), "branch", "--show-current"]);
    assert_eq!(head.trim(), "implement-119", "the primary checkout was moved off it:\n{}", run.text());
    let want = format!("  {}  moved since the plan, not removed: {} now holds implement-119", planned.display(), r.display());
    assert!(run.has(&want), "{}", run.text());
    assert!(run.has("reap summary: 1 reaped, 1 skipped"), "{}", run.text());
}

#[test]
fn a_branch_with_no_holder_at_all_since_the_plan_still_reaps() {
    // #881: the re-check refuses a holder that is not the planned workspace;
    // no holder at all is the vanished-worktree case and still cleans up.
    let c = Cleanup::new();
    let r = reap_repo(&c, "r44", &["118", "119"]);
    let planned = r.join(".claude/worktrees/implement-119");
    let hook = r.join(".git/hooks/pre-push");
    std::fs::write(
        &hook,
        format!("#!/bin/sh\nunset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE\ngit -C {} worktree remove --force {} || true\n", r.display(), planned.display()),
    )
    .unwrap();
    std::fs::set_permissions(&hook, std::os::unix::fs::PermissionsExt::from_mode(0o755)).unwrap();

    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!c.has_branch(&r, "implement-119"), "{}", run.text());
    assert!(run.has("reap summary: 2 reaped, 0 skipped"), "{}", run.text());
}

#[test]
fn a_workspace_whose_path_resolves_outside_the_repo_is_not_a_candidate() {
    // The boundary the Codex pass on PR #878 asked about. git resolves a
    // worktree's path when it registers it, so `git worktree add` through a
    // symlink under .claude/worktrees/ records the outside path — this test
    // states the boundary, and the containment check resolving both sides is
    // what keeps it true if git's own spelling ever changes.
    let c = Cleanup::new();
    let r = reap_repo(&c, "r43", &["120"]);
    let outside = c.root().join("r43-outside");
    std::fs::create_dir_all(&outside).unwrap();
    c.mk_implement_branch(&r, "121");
    std::os::unix::fs::symlink(&outside, r.join(".claude/worktrees/link")).unwrap();
    c.worktree_add(&r, &[s(&r.join(".claude/worktrees/link/implement-121")), "implement-121"]);

    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok && run.has("reap plan: 1 implement-* workspace(s) under"), "{}", run.text());
    assert!(outside.join("implement-121").is_dir() && c.has_branch(&r, "implement-121"), "{}", run.text());
    assert!(!run.has("implement-121"), "{}", run.text());
    assert!(!r.join(".claude/worktrees/implement-120").exists(), "{}", run.text());
}

#[test]
fn a_workspace_whose_directory_is_already_gone_still_has_its_branch_cleaned_up() {
    // resolved_under falls back to the parent for exactly this: git still
    // registers a workspace whose folder was deleted by hand, and it is
    // still a candidate.
    let c = Cleanup::new();
    let r = reap_repo(&c, "r44", &["122"]);
    let wt = r.join(".claude/worktrees/implement-122");
    std::fs::remove_dir_all(&wt).unwrap();
    let run = c.mc(Tools::Full, &["--reap", "--repo", s(&r), "--yes"], &[]);
    assert!(run.ok, "{}", run.text());
    assert!(!c.has_branch(&r, "implement-122"), "{}", run.text());
    assert!(run.has(&format!("  {}  reaped", wt.display())), "{}", run.text());
}
