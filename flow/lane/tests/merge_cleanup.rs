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
fn the_deleted_tip_is_recorded_under_refs_deleted() {
    let c = Cleanup::new();
    let r = c.mkfixture("r1");
    let tip = c.rev(&r, "caneff/merged-one");
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(run.ok, "{}", run.text());
    assert_eq!(c.rev(&r, "refs/deleted/caneff/merged-one"), tip);
    assert!(run.has("refs/deleted/caneff/merged-one"), "{}", run.text());
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

// --- argument handling -------------------------------------------------------

#[test]
fn help_prints_the_header_and_exits_zero() {
    let c = Cleanup::new();
    let run = c.mc(Tools::Full, &["--help"], &[]);
    assert!(run.ok);
    assert!(run.stdout.starts_with("The tail Chris hand-ran after every squash merge"), "{}", run.stdout);
    assert!(run.stdout.contains("  merge-cleanup --sweep [--root <dir>] [--yes] [--dry-run]\n"), "{}", run.stdout);
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

#[test]
fn a_live_registry_pid_in_the_workspace_refuses() {
    let c = Cleanup::new();
    let (r, wt) = lane_workspace(&c, "r6", "implement-1");
    c.session("live", &format!(r#"{{"pid":{},"cwd":"{}"}}"#, me(), wt.display()));
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
    c.session("sibling", &format!(r#"{{"pid":{},"cwd":"{}"}}"#, me(), wts.join("agent-live").display()));
    c.session("prefix", &format!(r#"{{"pid":{},"cwd":"{}0"}}"#, me(), wt.display()));
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
    c.session("r11", &format!(r#"{{"pid":{},"cwd":"{}"}}"#, me(), wt.display()));
    let run = c.mc(Tools::NoHerdr, &["--repo", s(&r), "caneff/merged-one"], &[]);
    assert!(!run.ok && run.has(&format!("pid {}", me())) && wt.is_dir(), "{}", run.text());
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
    c.session("r16", &format!(r#"{{"pid":{},"cwd":"{}","sessionId":"sess-16-unmatched"}}"#, me(), wt.display()));
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
fn a_sweep_answered_n_at_the_terminal_deletes_nothing() {
    let c = Cleanup::new();
    let root = sweep_root(&c);
    let run = c.mc_tty(Tools::Full, &["--sweep", "--root", s(&root)], "n\n");
    assert!(!run.ok && run.terminal.contains("nothing deleted (answer y, or pass --yes)"), "{}", run.terminal);
    assert!(!run.terminal.contains("stdin is not a terminal"), "{}", run.terminal);
    assert!(c.has_branch(&root.join("other"), "caneff/merged-one"));
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
    assert!(run.ok && run.has("flow/lane changed: rebuilding the lane binaries"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "ran\n");
    assert_eq!(std::fs::read_to_string(&bin).unwrap(), "NEW\n");
}

#[test]
fn skips_the_rebuild_when_the_pull_did_not_touch_the_crate() {
    let c = Cleanup::new();
    let (log, bin) = lane_env(&c);
    let r = c.mk_lane_repo("r18", false);
    let run = c.mc(Tools::Full, &["--repo", s(&r), "caneff/trivial"], &[("LANE_INSTALL_LOG", &log), ("LANE_INSTALLED_BIN", &bin)]);
    assert!(run.ok && !run.has("rebuilding the lane binaries"), "{}", run.text());
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "");
    assert_eq!(std::fs::read_to_string(&bin).unwrap(), "OLD\n");
    assert_eq!(c.rev(&r, "main"), c.rev(&r, "origin/main"));
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
    assert_eq!(std::fs::read_to_string(&log).unwrap(), "");
}
