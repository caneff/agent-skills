//! Contract tests for the `implement-dispatch` binary, against a scratch
//! origin/clone and the fake `gh`/`herdr` from `lane-fake` — the same seam
//! the bash suite it replaces used. Covers every case in
//! `flow/bin/implement-dispatch.test.sh`.

mod support;
use support::{default_scenario, out_text, with, Fixture};

fn refused(out: &std::process::Output, calls: &str, repo: &std::path::Path, n: &str, want: &str) -> bool {
    let text = out_text(out).to_lowercase();
    !out.status.success()
        && text.contains(&want.to_lowercase())
        && !calls.contains("worktree open")
        && !calls.contains("issue edit")
        && !std::path::Path::new(&format!("{}/.git/refs/heads/implement-{n}", repo.display())).exists()
        && !std::path::Path::new(&format!("{}/.git/refs/heads/spec-{n}", repo.display())).exists()
}

#[test]
fn refuses_when_no_herdr_server_is_running() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("HERDR_RUNNING", "false")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "herdr server"), "{}", out_text(&out));
}

#[test]
fn refuses_when_claude_onboarding_is_not_complete() {
    let f = Fixture::new();
    f.reset_home(false);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "395", "onboarding"), "{}", out_text(&out));
}

#[test]
fn refuses_a_closed_issue() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_STATE", "CLOSED")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "not an open issue"), "{}", out_text(&out));
}

#[test]
fn refuses_a_missing_issue() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_STATE", "")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "not an open issue"), "{}", out_text(&out));
}

#[test]
fn refuses_an_origin_that_names_no_github_owner_name() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("notgithub", "main");
    std::process::Command::new("git")
        .args(["-C", repo.to_str().unwrap(), "remote", "set-url", "origin", "/elsewhere/notgithub.git"])
        .status()
        .unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "395", "owner/name"), "{}", out_text(&out));
    assert!(!f.calls().lines().any(|l| l.starts_with("gh ")), "gh was called without an owner/name: {}", f.calls());
}

#[test]
fn refuses_when_flock_is_not_on_path() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    // A PATH with the fake dir and every real tool except flock.
    let noflock = f.tmp.path().join("noflock");
    std::fs::create_dir_all(&noflock).unwrap();
    for t in ["git"] {
        let p = which(t);
        std::os::unix::fs::symlink(p, noflock.join(t)).unwrap();
    }
    std::os::unix::fs::symlink(support::bin_path(), f.tmp.path().join("bin/implement-dispatch-noop")).ok();
    let out = std::process::Command::new(support::bin_path())
        .args(["--repo", repo.to_str().unwrap(), "395"])
        .env_clear()
        .env("PATH", format!("{}:{}", noflock.display(), f.tmp.path().join("bin").display()))
        .env("HOME", f.home())
        .env("CALL_LOG", f.call_log())
        .envs(default_scenario())
        .output()
        .unwrap();
    assert!(refused(&out, &f.calls(), &repo, "395", "flock is not on path"), "{}", out_text(&out));
}

fn which(name: &str) -> std::path::PathBuf {
    let path = std::env::var("PATH").unwrap();
    std::env::split_paths(&path).map(|d| d.join(name)).find(|p| p.is_file()).unwrap()
}

#[test]
fn refuses_an_issue_not_labelled_ready_for_agent() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "in-progress")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "ready-for-agent"), "{}", out_text(&out));
}

#[test]
fn refuses_a_ready_for_agent_issue_that_is_also_held() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "ready-for-agent,in-progress")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "in-progress"), "{}", out_text(&out));
}

#[test]
fn refuses_when_herdr_agent_name_is_already_taken() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("HERDR_AGENT_TAKEN", "1")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &scenario);
    assert!(
        refused(&out, &f.calls(), &repo, "395", "sudokumaker-custom-constrain-395"),
        "{}",
        out_text(&out)
    );
}

#[test]
fn refuses_when_the_workspace_path_exists() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    std::fs::create_dir_all(repo.join(".claude/worktrees/implement-395")).unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "395", "already exists"), "{}", out_text(&out));
}

#[test]
fn refuses_when_git_still_registers_a_worktree_at_the_path() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    std::process::Command::new("git")
        .args(["-C", repo.to_str().unwrap(), "worktree", "add", "-q", "--detach", ".claude/worktrees/implement-394", "main"])
        .status()
        .unwrap();
    std::fs::remove_dir_all(repo.join(".claude/worktrees/implement-394")).unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "394"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "394", "already exists"), "{}", out_text(&out));
}

#[test]
fn refuses_when_the_branch_exists() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    std::process::Command::new("git").args(["-C", repo.to_str().unwrap(), "branch", "implement-396", "main"]).status().unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "396"], &default_scenario());
    assert!(!out.status.success());
    assert!(out_text(&out).contains("already exists"), "{}", out_text(&out));
    assert!(!repo.join(".claude/worktrees/implement-396").exists());
    assert!(!f.calls().contains("worktree open") && !f.calls().contains("issue edit"));
}

#[test]
fn creates_the_workspace_and_branch_off_origin_default_with_no_origin_head() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    // no origin/HEAD in this fixture
    let head_ref = std::process::Command::new("git")
        .args(["-C", repo.to_str().unwrap(), "symbolic-ref", "-q", "refs/remotes/origin/HEAD"])
        .output()
        .unwrap();
    assert!(!head_ref.status.success(), "fixture unexpectedly has origin/HEAD");

    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "dispatch failed: {}", out_text(&out));

    let wt = repo.join(".claude/worktrees/implement-395");
    let branch = String::from_utf8(
        std::process::Command::new("git").args(["-C", wt.to_str().unwrap(), "branch", "--show-current"]).output().unwrap().stdout,
    )
    .unwrap();
    assert_eq!(branch.trim(), "implement-395");
    let wt_head =
        String::from_utf8(std::process::Command::new("git").args(["-C", wt.to_str().unwrap(), "rev-parse", "HEAD"]).output().unwrap().stdout).unwrap();
    let origin_main = String::from_utf8(
        std::process::Command::new("git").args(["-C", repo.to_str().unwrap(), "rev-parse", "origin/main"]).output().unwrap().stdout,
    )
    .unwrap();
    assert_eq!(wt_head, origin_main);
}

#[test]
fn writes_the_trust_key_for_exactly_the_new_path() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let wt = repo.join(".claude/worktrees/implement-395");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    let raw = std::fs::read_to_string(f.home().join(".claude.json")).unwrap();
    let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let projects = v.get("projects").unwrap().as_object().unwrap();
    let mut keys: Vec<&str> = projects.keys().map(String::as_str).collect();
    keys.sort();
    let mut expected = vec!["/elsewhere", wt.to_str().unwrap()];
    expected.sort();
    assert_eq!(keys, expected);
    assert_eq!(projects[wt.to_str().unwrap()]["hasTrustDialogAccepted"], true);
    assert_eq!(projects["/elsewhere"]["hasTrustDialogAccepted"], false);
    assert_eq!(v["hasCompletedOnboarding"], true);
}

#[test]
fn calls_open_start_prompt_in_order_with_the_truncated_agent_name() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let wt = repo.join(".claude/worktrees/implement-395");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    let calls = f.calls();
    let herdr_calls: Vec<&str> = calls
        .lines()
        .filter(|l| l.starts_with("herdr worktree open") || l.starts_with("herdr agent start") || l.starts_with("herdr agent prompt"))
        .collect();
    let name = "sudokumaker-custom-constrain-395";
    let expected = vec![
        format!(
            "herdr worktree open --cwd {} --path {} --label implement-395 --no-focus --trust-repository",
            repo.display(),
            wt.display()
        ),
        format!("herdr agent start {name} --kind claude --pane w7:p1 -- --model sonnet"),
        format!("herdr agent prompt {name} /implement 395 --tier heavy --controller \"skills-ctl\" --wait --until working --timeout 120000"),
    ];
    assert_eq!(herdr_calls, expected, "herdr calls wrong:\n{herdr_calls:?}");
}

#[test]
fn every_gh_call_names_the_repo_from_origin_and_claims_the_ticket() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let calls = f.calls();
    for line in calls.lines().filter(|l| l.starts_with("gh ")) {
        assert!(line.contains("--repo caneff/sudokumaker-custom-constraints"), "a gh call relied on the cwd: {line}");
    }
    assert!(
        calls.contains("gh issue edit 395 --repo caneff/sudokumaker-custom-constraints --remove-label ready-for-agent --add-label in-progress --add-assignee @me"),
        "ticket not claimed: {calls}"
    );
}

#[test]
fn the_report_names_path_branch_agent_and_the_cleanup_line() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let wt = repo.join(".claude/worktrees/implement-395");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let text = out_text(&out);
    assert!(text.contains(&format!("worktree: {}", wt.display())), "{text}");
    assert!(text.contains("branch:   implement-395"), "{text}");
    assert!(text.contains("agent:    sudokumaker-custom-constrain-395"), "{text}");
    assert!(text.contains(&format!("cd {} && merge-cleanup implement-395 --repo {}", repo.display(), repo.display())), "{text}");
}

// --- #819: the report also names the worker's Claude session -------------

const AGENT_395: &str = "sudokumaker-custom-constrain-395";

/// A real, live child process — what a real Claude session's pid would be,
/// so the registry file's alive check has something real to check.
fn spawn_live() -> std::process::Child {
    std::process::Command::new("sleep").arg("30").spawn().unwrap()
}

#[test]
fn the_report_names_the_workers_claude_session_beside_the_herdr_agent() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let wt = repo.join(".claude/worktrees/implement-395");
    // herdr reports which sessionId it attached to the agent this run just
    // started; the registry file carrying that same sessionId is the
    // worker's, the way merge-cleanup already resolves occupancy.
    f.set_agents(&format!(r#"[{{"name":"{AGENT_395}","agent_session":{{"value":"sess-395"}}}}]"#));
    let mut child = spawn_live();
    let proc_start = lane::proc_info::read_stat(child.id() as i32).unwrap().start;
    std::fs::write(
        f.home().join(".claude/sessions").join(format!("{}.json", child.id())),
        format!(
            r#"{{"pid":{},"cwd":"{}","name":"implement-395-42","sessionId":"sess-395","procStart":"{proc_start}"}}"#,
            child.id(),
            wt.display()
        ),
    )
    .unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    let _ = child.kill();
    let _ = child.wait();
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("session:  implement-395-42"), "{}", out_text(&out));
}

#[test]
fn no_matching_herdr_agent_session_reports_unavailable_instead_of_failing() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("session:  (unavailable)"), "{}", out_text(&out));
}

#[test]
fn a_non_worker_session_sharing_the_worktree_and_sorting_first_is_not_reported() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let wt = repo.join(".claude/worktrees/implement-395");
    f.set_agents(&format!(r#"[{{"name":"{AGENT_395}","agent_session":{{"value":"sess-worker"}}}}]"#));
    // Two live sessions share the worktree's cwd: a stray one (someone else
    // attached a session in the same workspace) and the real worker. The
    // stray one's registry file is named to sort first regardless of the
    // two real pids, the way live_in's own file-name order could otherwise
    // pick it — only the herdr-reported sessionId decides which one wins.
    let mut other = spawn_live();
    let mut worker = spawn_live();
    let other_start = lane::proc_info::read_stat(other.id() as i32).unwrap().start;
    let worker_start = lane::proc_info::read_stat(worker.id() as i32).unwrap().start;
    std::fs::write(
        f.home().join(".claude/sessions").join("0000000001.json"),
        format!(
            r#"{{"pid":{},"cwd":"{}","name":"not-the-worker","sessionId":"sess-other","procStart":"{other_start}"}}"#,
            other.id(),
            wt.display()
        ),
    )
    .unwrap();
    std::fs::write(
        f.home().join(".claude/sessions").join(format!("{}.json", worker.id())),
        format!(
            r#"{{"pid":{},"cwd":"{}","name":"implement-395-42","sessionId":"sess-worker","procStart":"{worker_start}"}}"#,
            worker.id(),
            wt.display()
        ),
    )
    .unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    let _ = other.kill();
    let _ = other.wait();
    let _ = worker.kill();
    let _ = worker.wait();
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(
        out_text(&out).contains("session:  implement-395-42"),
        "the non-worker session sorting first should not be reported: {}",
        out_text(&out)
    );
}

#[test]
fn a_live_matching_session_with_no_name_key_at_all_reports_unavailable() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let wt = repo.join(".claude/worktrees/implement-395");
    f.set_agents(&format!(r#"[{{"name":"{AGENT_395}","agent_session":{{"value":"sess-395"}}}}]"#));
    // A live, sessionId-matching registry file with no "name" key at all —
    // real files sometimes lack it.
    let mut child = spawn_live();
    std::fs::write(
        f.home().join(".claude/sessions").join(format!("{}.json", child.id())),
        format!(r#"{{"pid":{},"cwd":"{}","sessionId":"sess-395"}}"#, child.id(), wt.display()),
    )
    .unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    let _ = child.kill();
    let _ = child.wait();
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(
        out_text(&out).contains("session:  (unavailable)"),
        "a nameless session should report (unavailable), not a blank name: {}",
        out_text(&out)
    );
}

#[test]
fn model_reaches_agent_start_and_pane_falls_back_to_pane_list() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("HERDR_NO_ROOT_PANE", "1")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--model", "opus", "397"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(
        f.calls().lines().any(|l| l == "herdr agent start sudokumaker-custom-constrain-397 --kind claude --pane w8:p3 -- --model opus"),
        "{}",
        f.calls()
    );
}

#[test]
fn refuses_a_model_other_than_sonnet_or_opus() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--model", "haiku", "398"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "398", "model"), "{}", out_text(&out));
}

#[test]
fn a_flag_with_no_value_is_refused_not_looped_on() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["398", "--model"], &default_scenario());
    assert!(!out.status.success());
    assert!(out_text(&out).contains("--model needs a value"), "{}", out_text(&out));
    let _ = repo;
}

#[test]
fn a_documentation_label_puts_tier_light_in_the_brief() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "documentation,ready-for-agent")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "403"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(
        f.calls().lines().any(|l| l
            == "herdr agent prompt sudokumaker-custom-constrain-403 /implement 403 --tier light --controller \"skills-ctl\" --wait --until working --timeout 120000"),
        "{}",
        f.calls()
    );
}

#[test]
fn controller_flag_overrides_the_session_registry() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--controller", "other-9", "404"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(
        f.calls().lines().any(|l| l
            == "herdr agent prompt sudokumaker-custom-constrain-404 /implement 404 --tier heavy --controller \"other-9\" --wait --until working --timeout 120000"),
        "{}",
        f.calls()
    );
}

#[test]
fn refuses_when_no_controller_session_is_found_and_none_is_named() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    std::fs::remove_file(f.session_file()).unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "405"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "405", "controller"), "{}", out_text(&out));
}

#[test]
fn skips_a_session_file_whose_procstart_is_not_the_live_process() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    f.set_session("skills-ctl", "1");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "406"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "406", "controller"), "{}", out_text(&out));
}

#[test]
fn a_controller_name_with_spaces_reaches_the_brief_whole_quoted() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    f.set_session("bank drill composition", &f.own_proc_start());
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "407"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(
        f.calls().lines().any(|l| l
            == "herdr agent prompt sudokumaker-custom-constrain-407 /implement 407 --tier heavy --controller \"bank drill composition\" --wait --until working --timeout 120000"),
        "{}",
        f.calls()
    );
}

#[test]
fn refuses_a_controller_name_holding_a_double_quote() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--controller", "say \"hi\"", "408"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "408", "controller"), "{}", out_text(&out));
}

#[test]
fn the_base_is_origin_master_when_origin_has_no_main_and_no_head() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("masteronly", "master");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "401"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let wt = repo.join(".claude/worktrees/implement-401");
    let wt_head =
        String::from_utf8(std::process::Command::new("git").args(["-C", wt.to_str().unwrap(), "rev-parse", "HEAD"]).output().unwrap().stdout).unwrap();
    let origin_master =
        String::from_utf8(std::process::Command::new("git").args(["-C", repo.to_str().unwrap(), "rev-parse", "origin/master"]).output().unwrap().stdout)
            .unwrap();
    assert_eq!(wt_head, origin_master);
}

#[test]
fn refuses_when_the_resolved_base_is_not_on_origin() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("trunkonly", "trunk");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "402"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "402", "origin/main"), "{}", out_text(&out));
}

#[test]
fn a_stalled_prompt_exits_non_zero_with_herdrs_error_and_leaves_the_worktree() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("HERDR_STALL", "1")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "399"], &scenario);
    assert!(!out.status.success());
    assert!(out_text(&out).contains("agent_prompt_stalled"), "{}", out_text(&out));
    assert!(repo.join(".claude/worktrees/implement-399").is_dir());
}

#[test]
fn two_concurrent_dispatches_both_leave_their_trust_keys() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo_a = f.mkfixture("race-a", "main");
    let repo_b = f.mkfixture("race-b", "main");
    // Holds each dispatch's seed-trust critical section open long enough that,
    // without the flock, both would read ~/.claude.json before either writes
    // it back — the only way this test can actually witness the lock instead
    // of passing by luck on how fast two processes happen to interleave.
    let scenario = with(&default_scenario(), &[("LANE_SEED_TRUST_DELAY_MS", "200")]);
    let (out_a, out_b) = std::thread::scope(|s| {
        let ta = s.spawn(|| f.dispatch(&["--repo", repo_a.to_str().unwrap(), "501"], &scenario));
        let tb = s.spawn(|| f.dispatch(&["--repo", repo_b.to_str().unwrap(), "502"], &scenario));
        (ta.join().unwrap(), tb.join().unwrap())
    });
    assert!(out_a.status.success(), "{}", out_text(&out_a));
    assert!(out_b.status.success(), "{}", out_text(&out_b));

    let raw = std::fs::read_to_string(f.home().join(".claude.json")).unwrap();
    let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let wt_a = repo_a.join(".claude/worktrees/implement-501");
    let wt_b = repo_b.join(".claude/worktrees/implement-502");
    assert_eq!(v["projects"][wt_a.to_str().unwrap()]["hasTrustDialogAccepted"], true, "{raw}");
    assert_eq!(v["projects"][wt_b.to_str().unwrap()]["hasTrustDialogAccepted"], true, "{raw}");
    assert!(v["projects"]["/elsewhere"].is_object(), "{raw}");
}

#[test]
fn the_trust_pre_seed_keeps_claude_jsons_original_permissions() {
    use std::os::unix::fs::PermissionsExt;
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let claude_json = f.home().join(".claude.json");
    std::fs::set_permissions(&claude_json, std::fs::Permissions::from_mode(0o600)).unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let mode = std::fs::metadata(&claude_json).unwrap().permissions().mode() & 0o777;
    assert_eq!(mode, 0o600, "the rewrite widened ~/.claude.json's permissions");
}

#[test]
fn an_empty_controller_flag_falls_back_to_the_session_registry() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--controller", "", "409"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(
        f.calls().lines().any(|l| l
            == "herdr agent prompt sudokumaker-custom-constrain-409 /implement 409 --tier heavy --controller \"skills-ctl\" --wait --until working --timeout 120000"),
        "an empty --controller should fall back to the session name, not dispatch with an empty one: {}",
        f.calls()
    );
}

// --- #758: a closed stdout stops the run instead of panicking ----------------

#[test]
fn a_reader_that_closes_early_gets_a_clean_nonzero_exit_no_panic_text() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let (code, stderr) = f.dispatch_broken_pipe(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert_eq!(code, Some(lane::io_safe::BROKEN_PIPE_EXIT), "stderr: {stderr}");
    assert!(!stderr.contains("panicked"), "{stderr}");
    assert!(!stderr.contains("Broken pipe"), "{stderr}");
}


// --- #787: --spec dispatches a nested /implement-spec run -------------------

#[test]
fn spec_mode_briefs_implement_spec_in_a_spec_workspace() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let wt = repo.join(".claude/worktrees/spec-395");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "395", "--slots", "3"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));

    let branch = String::from_utf8(
        std::process::Command::new("git").args(["-C", wt.to_str().unwrap(), "branch", "--show-current"]).output().unwrap().stdout,
    )
    .unwrap();
    assert_eq!(branch.trim(), "spec-395");
    let calls = f.calls();
    let herdr_calls: Vec<&str> = calls
        .lines()
        .filter(|l| l.starts_with("herdr worktree open") || l.starts_with("herdr agent start") || l.starts_with("herdr agent prompt"))
        .collect();
    // 32 chars exactly: the repo part is cut to make room for "-spec-395".
    let name = "sudokumaker-custom-cons-spec-395";
    assert_eq!(name.len(), 32);
    let expected = vec![
        format!("herdr worktree open --cwd {} --path {} --label spec-395 --no-focus --trust-repository", repo.display(), wt.display()),
        format!("herdr agent start {name} --kind claude --pane w7:p1 -- --model opus"),
        format!("herdr agent prompt {name} /implement-spec 395 --slots 3 --controller \"skills-ctl\" --wait --until working --timeout 120000"),
    ];
    assert_eq!(herdr_calls, expected, "herdr calls wrong:\n{herdr_calls:?}");
    assert!(
        calls.contains("gh issue edit 395 --repo caneff/sudokumaker-custom-constraints --remove-label ready-for-agent --add-label in-progress --add-assignee @me"),
        "ticket not claimed: {calls}"
    );
    assert!(out_text(&out).contains("merge-cleanup spec-395"), "{}", out_text(&out));
    assert!(out_text(&out).contains("dispatched #395 (opus, spec, 3 slots, controller skills-ctl)"), "{}", out_text(&out));
}

#[test]
fn spec_mode_without_slots_defaults_to_five_in_the_brief() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "395"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(f.calls().contains("/implement-spec 395 --slots 5 --controller"), "{}", f.calls());
    assert!(out_text(&out).contains("spec, 5 slots"), "{}", out_text(&out));
}

#[test]
fn slots_without_spec_mode_is_refused() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--slots", "3", "395"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "395", "--slots"), "{}", out_text(&out));
}

#[test]
fn slots_that_is_not_a_positive_integer_is_refused() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent")]);
    for bad in ["three", "0", "-1", ""] {
        let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "395", "--slots", bad], &scenario);
        assert!(refused(&out, &f.calls(), &repo, "395", "--slots"), "--slots {bad:?}: {}", out_text(&out));
    }
}

#[test]
fn spec_mode_refuses_an_issue_without_the_spec_label() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "395", "--slots", "3"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "395", "not labelled spec"), "{}", out_text(&out));
}

#[test]
fn plain_mode_refuses_a_spec_labelled_issue_naming_spec_mode() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "--spec"), "{}", out_text(&out));
    assert!(!repo.join(".claude/worktrees/implement-395").exists());
}

#[test]
fn spec_mode_still_refuses_a_held_issue() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent,in-progress")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "395", "--slots", "3"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "in-progress"), "{}", out_text(&out));
}

#[test]
fn help_documents_both_modes() {
    let f = Fixture::new();
    let out = f.dispatch(&["--help"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let text = out_text(&out);
    for want in [
        "<issue number> [<issue number>...]",
        "/implement <n>... --tier",
        "--spec <n> [--slots <k>]",
        "/implement-spec <n> --slots <k>",
        "spec-<n>",
        "ready-for-human",
        "--chris-merges",
        "Several issue numbers are one clump",
        "a clump is always heavy",
        "for the lowest number named",
    ] {
        assert!(text.contains(want), "help lacks {want:?}:\n{text}");
    }
}

// --- #794: a ready-for-human ticket dispatches, and Chris merges it ----------

#[test]
fn a_ready_for_human_ticket_is_claimed_and_briefed_as_chris_merges() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "enhancement,ready-for-human")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "410"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    let calls = f.calls();
    assert!(
        calls.lines().any(|l| l
            == "gh issue edit 410 --repo caneff/sudokumaker-custom-constraints --add-label in-progress --add-assignee @me"),
        "ready-for-human ticket not claimed with ready-for-human kept: {calls}"
    );
    assert!(
        !calls.lines().any(|l| l.contains("--remove-label ready-for-human")),
        "claim removed ready-for-human, but it must survive the build as the Chris-merges signal: {calls}"
    );
    assert!(
        calls.lines().any(|l| l
            == "herdr agent prompt sudokumaker-custom-constrain-410 /implement 410 --tier heavy --controller \"skills-ctl\" --chris-merges --wait --until working --timeout 120000"),
        "{calls}"
    );
    assert!(out_text(&out).contains("dispatched #410 (sonnet, heavy tier, Chris merges, controller skills-ctl)"), "{}", out_text(&out));
}

#[test]
fn a_failure_past_the_claim_on_a_ready_for_human_ticket_only_undoes_in_progress() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "ready-for-human"), ("HERDR_STALL", "1")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "411"], &scenario);
    assert!(!out.status.success());
    assert!(
        out_text(&out)
            .contains("release the ticket: gh issue edit 411 --repo caneff/sudokumaker-custom-constraints --remove-label in-progress"),
        "{}",
        out_text(&out)
    );
    assert!(
        !out_text(&out).contains("--add-label ready-for-human"),
        "release re-added ready-for-human, but the claim never removed it: {}",
        out_text(&out)
    );
}

#[test]
fn a_claimed_ready_for_human_ticket_still_refuses_a_second_dispatch() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    // What the ticket looks like mid-build: ready-for-human kept, in-progress added.
    let scenario = with(&default_scenario(), &[("GH_LABELS", "ready-for-human,in-progress")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "414"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "414", "in-progress"), "{}", out_text(&out));
}

#[test]
fn refuses_an_issue_labelled_both_ready_for_agent_and_ready_for_human() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "ready-for-agent,ready-for-human")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "412"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "412", "both"), "{}", out_text(&out));
}

#[test]
fn spec_mode_refuses_a_ready_for_human_issue() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-human")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "413", "--slots", "2"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "413", "ready-for-human"), "{}", out_text(&out));
}

#[test]
fn spec_mode_briefs_the_parsed_slot_count_and_honours_model() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "395", "--slots", "007", "--model", "sonnet"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    let calls = f.calls();
    let name = "sudokumaker-custom-cons-spec-395";
    assert!(calls.lines().any(|l| l == format!("herdr agent start {name} --kind claude --pane w7:p1 -- --model sonnet")), "{calls}");
    assert!(
        calls.lines().any(|l| l
            == format!("herdr agent prompt {name} /implement-spec 395 --slots 7 --controller \"skills-ctl\" --wait --until working --timeout 120000")),
        "{calls}"
    );
}

// --- #889: a clump — one workspace, every ticket claimed ---------------------

const SLUG: &str = "caneff/sudokumaker-custom-constraints";

fn claim_line(n: &str) -> String {
    format!("gh issue edit {n} --repo {SLUG} --remove-label ready-for-agent --add-label in-progress --add-assignee @me")
}

#[test]
fn a_clump_claims_every_ticket_and_names_one_workspace_for_the_lowest() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    // Named out of order on purpose: the lowest names the workspace, not
    // the first one typed.
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "421", "420", "422"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let calls = f.calls();
    for n in ["420", "421", "422"] {
        assert!(calls.lines().any(|l| l == claim_line(n)), "#{n} was not claimed: {calls}");
    }
    assert_eq!(calls.lines().filter(|l| l.starts_with("herdr worktree open")).count(), 1, "one workspace only: {calls}");
    assert!(calls.contains("--label implement-420"), "{calls}");
    assert!(repo.join(".claude/worktrees/implement-420").is_dir(), "{calls}");
    assert!(!repo.join(".claude/worktrees/implement-421").exists(), "{calls}");
    assert!(out_text(&out).contains("dispatched #420 #421 #422 (sonnet, heavy tier, controller skills-ctl)"), "{}", out_text(&out));
    assert!(out_text(&out).contains("branch:   implement-420"), "{}", out_text(&out));
}

#[test]
fn a_clumps_brief_carries_every_ticket_in_it() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "424", "423"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let prefix = "herdr agent prompt sudokumaker-custom-constrain-423 /implement 423 424 --tier heavy --controller \"skills-ctl\"";
    let tail = " --wait --until working --timeout 120000";
    assert!(f.calls().lines().any(|l| l.starts_with(prefix) && l.ends_with(tail)), "{}", f.calls());
}

// --- #901: what the clump brief tells the worker ------------------------------

fn prompt_line(f: &Fixture) -> String {
    f.calls().lines().find(|l| l.starts_with("herdr agent prompt")).unwrap_or_default().to_string()
}

#[test]
fn a_clumps_brief_says_internal_blockers_are_ignored_shas_do_not_survive_a_squash_and_the_report_is_one() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "424", "423"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let line = prompt_line(&f);
    for needle in [
        "a blocker that is another ticket of this clump is ignored",
        "per-ticket shas do not survive the squash merge",
        "the PR-up report is one report for the clump, not one per ticket",
    ] {
        assert!(line.contains(needle), "clump brief lacks {needle:?}: {line}");
    }
}

#[test]
fn a_single_tickets_brief_carries_no_clump_note() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "423"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let line = prompt_line(&f);
    // Equality, not absence: an empty line (no prompt sent) must not pass.
    assert_eq!(
        line,
        "herdr agent prompt sudokumaker-custom-constrain-423 /implement 423 --tier heavy --controller \"skills-ctl\" --wait --until working --timeout 120000"
    );
}

#[test]
fn a_clump_holding_one_unclaimable_ticket_claims_nothing() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_ISSUE_427", "OPEN\tready-for-agent,in-progress\t")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "425", "426", "427"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "425", "#427 is labelled in-progress"), "{}", out_text(&out));
}

#[test]
fn a_claim_that_fails_partway_releases_the_tickets_already_claimed() {
    // The claim is one gh call per ticket, so "no partial claim" cannot be a
    // pre-check alone: a call that fails after its siblings succeeded has to
    // put them back.
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_ISSUE_EDIT_FAIL", "430")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "428", "429", "430"], &scenario);
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("could not claim #430"), "{}", out_text(&out));
    let calls = f.calls();
    for n in ["428", "429"] {
        assert!(
            calls.lines().any(|l| l
                == format!("gh issue edit {n} --repo {SLUG} --remove-label in-progress --add-label ready-for-agent --remove-assignee @me")),
            "#{n} was claimed and never released: {calls}"
        );
    }
    assert!(!calls.contains("worktree open"), "{calls}");
    assert!(!repo.join(".claude/worktrees/implement-428").exists(), "{calls}");
}

#[test]
fn a_clump_is_always_heavy_even_when_every_ticket_is_documentation() {
    // Light tier lands straight on the default branch with no PR, and the
    // merged PR's closingIssuesReferences is the only record merge-cleanup
    // can clear a clump's claims from — so a light clump would land with
    // every ticket but the branch's own still claimed.
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let docs = "OPEN\tdocumentation,ready-for-agent\t";
    let all_docs = with(&default_scenario(), &[("GH_ISSUE_431", docs), ("GH_ISSUE_432", docs)]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "431", "432"], &all_docs);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(f.calls().contains("/implement 431 432 --tier heavy"), "{}", f.calls());
    assert!(!f.calls().contains("--tier light"), "{}", f.calls());

    // One documentation ticket is unchanged: still light.
    let f2 = Fixture::new();
    f2.reset_home(true);
    let repo2 = f2.mkfixture("sudokumaker-custom-constraints", "main");
    let one = with(&default_scenario(), &[("GH_ISSUE_433", docs)]);
    let out2 = f2.dispatch(&["--repo", repo2.to_str().unwrap(), "433"], &one);
    assert!(out2.status.success(), "{}", out_text(&out2));
    assert!(f2.calls().contains("/implement 433 --tier light"), "{}", f2.calls());
}

#[test]
fn a_clump_holding_a_ready_for_human_ticket_is_briefed_chris_merges() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_ISSUE_436", "OPEN\tenhancement,ready-for-human\t")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "435", "436"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    let calls = f.calls();
    assert!(calls.lines().any(|l| l == claim_line("435")), "{calls}");
    assert!(
        calls.lines().any(|l| l == format!("gh issue edit 436 --repo {SLUG} --add-label in-progress --add-assignee @me")),
        "ready-for-human must survive the claim: {calls}"
    );
    assert!(calls.contains("/implement 435 436 --tier heavy --controller \"skills-ctl\" --chris-merges"), "{calls}");
    assert!(out_text(&out).contains("dispatched #435 #436 (sonnet, heavy tier, Chris merges, controller skills-ctl)"), "{}", out_text(&out));
}

#[test]
fn the_same_ticket_named_twice_is_refused() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "437", "437"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "437", "#437 is named twice"), "{}", out_text(&out));
}

#[test]
fn a_leading_zero_does_not_make_a_second_ticket() {
    // An issue number is the number: `007` and `7` are one ticket. Compared
    // as text they are two, and the clump would claim and brief the same
    // issue twice while `0437` named the branch.
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "0437", "437"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "437", "#437 is named twice"), "{}", out_text(&out));

    let f2 = Fixture::new();
    f2.reset_home(true);
    let repo2 = f2.mkfixture("sudokumaker-custom-constraints", "main");
    let out2 = f2.dispatch(&["--repo", repo2.to_str().unwrap(), "0438"], &default_scenario());
    assert!(out2.status.success(), "{}", out_text(&out2));
    assert!(f2.calls().contains("/implement 438 --tier"), "{}", f2.calls());
    assert!(repo2.join(".claude/worktrees/implement-438").is_dir(), "{}", f2.calls());
}

#[test]
fn spec_mode_still_takes_one_ticket_only() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "438", "--slots", "2", "439"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "438", "one ticket at a time"), "{}", out_text(&out));
}

fn claim_lock(f: &Fixture) -> std::path::PathBuf {
    f.home().join(".implement-dispatch-claim-caneff__claimrace.lock")
}

fn claim_edits(calls: &str, n: &str) -> usize {
    calls.lines().filter(|l| l.starts_with(&format!("gh issue edit {n} ")) && l.contains("--add-label in-progress")).count()
}

#[test]
fn two_overlapping_dispatches_of_one_ticket_claim_it_once() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("claimrace", "main");
    let claims = f.home().join("claims");
    std::fs::create_dir_all(&claims).unwrap();
    // Both dispatches must reach the reread immediately before the claim
    // edit together, before either can edit: a barrier at the fake gh's
    // second `issue view` of the ticket, independent of the lock — that
    // reread is the actual critical section the lock protects. With the
    // lock, the second run cannot reach its reread until the first finishes
    // claiming, so the barrier times out and it reads the claim; without
    // it, both reach the reread free and both claim.
    let barrier = f.home().join("barrier");
    std::fs::create_dir_all(&barrier).unwrap();
    let scenario = with(&default_scenario(), &[("GH_VIEW_BARRIER_DIR", barrier.to_str().unwrap()), ("GH_CLAIM_DIR", claims.to_str().unwrap())]);
    let (a, b) = std::thread::scope(|s| {
        let ta = s.spawn(|| f.dispatch(&["--repo", repo.to_str().unwrap(), "601"], &scenario));
        let tb = s.spawn(|| f.dispatch(&["--repo", repo.to_str().unwrap(), "601"], &scenario));
        (ta.join().unwrap(), tb.join().unwrap())
    });
    let ok = [&a, &b].iter().filter(|o| o.status.success()).count();
    assert_eq!(ok, 1, "{}\n---\n{}", out_text(&a), out_text(&b));
    assert_eq!(claim_edits(&f.calls(), "601"), 1, "{}", f.calls());
    let loser = if a.status.success() { &b } else { &a };
    assert!(out_text(loser).contains("#601 is labelled in-progress"), "{}", out_text(loser));
}

#[test]
fn a_held_claim_lock_refuses_naming_the_holder_and_claims_nothing() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("claimrace", "main");
    let lock = claim_lock(&f);
    std::fs::write(&lock, "pid 4242 claiming #601\n").unwrap();
    let mut holder = std::process::Command::new("flock").arg(&lock).args(["sleep", "5"]).spawn().unwrap();
    std::thread::sleep(std::time::Duration::from_millis(300));
    let scenario = with(&default_scenario(), &[("LANE_CLAIM_LOCK_WAIT_MS", "200")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "601"], &scenario);
    let _ = holder.kill();
    let _ = holder.wait();
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("pid 4242 claiming #601"), "{}", out_text(&out));
    assert!(!f.calls().contains("issue edit"), "{}", f.calls());
}

#[test]
fn an_abandoned_claim_lock_file_does_not_wedge_dispatch() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("claimrace", "main");
    // Content from a dead run, no flock held on it.
    std::fs::write(claim_lock(&f), "pid 999999 claiming #601\n").unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "601"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
}

#[test]
fn a_ticket_claimed_between_the_read_and_the_edit_is_refused_and_never_released() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("claimrace", "main");
    let claims = f.home().join("claims");
    std::fs::create_dir_all(&claims).unwrap();
    // #602 is claimed by someone else after the refusal pass read it free:
    // the fake hides the claim from the first view of it only.
    std::fs::write(claims.join("602"), "").unwrap();
    let scenario = with(
        &default_scenario(),
        &[("GH_CLAIM_DIR", claims.to_str().unwrap()), ("GH_ISSUE_602", "OPEN\tenhancement,ready-for-agent\t"), ("GH_CLAIM_HIDE_UNTIL_EDIT", "602")],
    );
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "601", "602"], &scenario);
    assert!(!out.status.success(), "{}", out_text(&out));
    let calls = f.calls();
    assert_eq!(claim_edits(&calls, "602"), 0, "{calls}");
    assert!(!calls.contains("gh issue edit 602 "), "released a ticket this run never claimed: {calls}");
}

#[test]
fn a_dispatch_writes_its_pid_and_tickets_into_the_claim_lock_note() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("claimrace", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "601"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let note = std::fs::read_to_string(claim_lock(&f)).unwrap();
    assert!(note.starts_with("pid ") && note.contains("claiming #601"), "{note}");
}

#[test]
fn a_held_claim_lock_with_no_note_says_so() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("claimrace", "main");
    let lock = claim_lock(&f);
    std::fs::write(&lock, "").unwrap();
    let mut holder = std::process::Command::new("flock").arg(&lock).args(["sleep", "5"]).spawn().unwrap();
    std::thread::sleep(std::time::Duration::from_millis(300));
    let scenario = with(&default_scenario(), &[("LANE_CLAIM_LOCK_WAIT_MS", "200")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "601"], &scenario);
    let _ = holder.kill();
    let _ = holder.wait();
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("holder's note not written"), "{}", out_text(&out));
}

fn hooks_dir(repo: &std::path::Path) -> std::path::PathBuf {
    repo.join(".git/hooks")
}

#[test]
fn dispatch_installs_the_identity_guard_and_a_worktree_commit_is_refused() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "dispatch failed: {}", out_text(&out));

    let wt = repo.join(".claude/worktrees/implement-395");
    std::fs::write(wt.join("g"), "x\n").unwrap();
    let git = |args: &[&str]| std::process::Command::new("git").arg("-C").arg(&wt).args(args).output().unwrap();
    git(&["add", "g"]);
    let bad = git(&["-c", "user.email=real@gmail.com", "commit", "-qm", "x"]);
    assert!(!bad.status.success(), "a foreign email committed: {}", out_text(&bad));
    assert!(String::from_utf8_lossy(&bad.stderr).contains("commit-identity guard"), "refusal did not name itself: {}", out_text(&bad));
    let good = git(&["commit", "-qm", "x"]);
    assert!(good.status.success(), "configured identity refused: {}", out_text(&good));
}

/// A repo already carrying *this build's own* pre-commit wrapper from an
/// earlier dispatch must be recognised as already-installed, byte-identity,
/// and not displaced (its bytes stay stable; it is still rewritten in place
/// so a lost executable bit is repaired, #1054). The hazard this guards (review finding C2 on #1006's own
/// diff, reproduced as a fork bomb): the pre-commit wrapper's own body
/// hard-codes the name it displaces a foreign hook to (`pre-commit.foreign`)
/// — so if a code change ever alters the wrapper's bytes without changing
/// what it actually needs to (here: an earlier draft added `"$@"` to the
/// guard's `exec` line, which pre-commit never uses), every already-
/// dispatched repo's own wrapper reads as "foreign" on the next dispatch,
/// gets displaced to `pre-commit.foreign`, and that displaced copy's body —
/// unaware it is not `pre-commit` any more — still checks for and calls
/// `pre-commit.foreign`, i.e. itself: self-reference, then recursion, then a
/// forked process for every commit.
#[test]
fn a_repo_already_carrying_this_builds_own_pre_commit_wrapper_is_not_displaced_on_redispatch() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    let current_wrapper = "#!/bin/sh\n# lane commit-identity guard wrapper (#934, hardened against a foreign hook that only appears to call the guard — #1009)\ndir=\"$(dirname \"$0\")\"\nif [ -e \"$dir/pre-commit.foreign\" ]; then\n  \"$dir/pre-commit.foreign\" \"$@\" || exit $?\nfi\nexec \"$dir/commit-identity-guard\"\n";
    std::fs::write(&hook, current_wrapper).unwrap();
    let mut perms = std::fs::metadata(&hook).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
    std::fs::set_permissions(&hook, perms).unwrap();

    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    assert_eq!(
        std::fs::read_to_string(&hook).unwrap(),
        current_wrapper,
        "an already-installed wrapper changed bytes instead of being recognised as ours — its bytes must stay stable across a dispatch that changes nothing pre-commit cares about"
    );
    let foreign_slot = hooks_dir(&repo).join("pre-commit.foreign");
    assert!(
        !foreign_slot.exists(),
        "a wrapper this build itself installs was displaced to pre-commit.foreign — the self-recursion hazard (#1006 C2)"
    );
    refuses_a_foreign_email_commit(&repo, "395");
}

/// A wrapper whose bytes still match but whose executable bit was cleared
/// after install (#1054): git silently ignores a non-executable hook, so a
/// byte-identical wrapper must still be repaired on the next dispatch, not
/// taken as "already ours" and left inert.
#[test]
fn a_byte_identical_wrapper_that_lost_its_executable_bit_is_repaired_on_redispatch() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    for slot in ["pre-commit", "pre-push"] {
        let hook = hooks_dir(&repo).join(slot);
        std::fs::set_permissions(&hook, std::os::unix::fs::PermissionsExt::from_mode(0o644)).unwrap();
    }

    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "396"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    for slot in ["pre-commit", "pre-push"] {
        let mode = std::os::unix::fs::PermissionsExt::mode(&std::fs::metadata(hooks_dir(&repo).join(slot)).unwrap().permissions());
        assert!(mode & 0o111 != 0, "{slot} left non-executable (mode {mode:o}) by a redispatch");
    }
    refuses_a_foreign_email_commit(&repo, "396");
}

/// The pre-commit guard (#934) never fires on a replayed commit — a cherry-
/// pick or rebase, exactly the gap #1006 files (its own probe: `-c
/// user.email=... rebase` rewrote a replayed commit's email with exit 0).
/// This is the end-to-end proof that the pre-push half installed alongside
/// it catches what pre-commit cannot: cherry-pick a commit under a foreign
/// committer email (never touching `git commit` at all), then push it.
#[test]
fn dispatch_installs_the_pre_push_guard_and_a_replayed_foreign_email_commit_is_refused_at_push() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "dispatch failed: {}", out_text(&out));

    let wt = repo.join(".claude/worktrees/implement-395");
    let git = |args: &[&str]| std::process::Command::new("git").arg("-C").arg(&wt).args(args).output().unwrap();

    std::fs::write(wt.join("g"), "x\n").unwrap();
    git(&["add", "g"]);
    assert!(git(&["commit", "-qm", "x"]).status.success());
    let sha = String::from_utf8(git(&["rev-parse", "HEAD"]).stdout).unwrap().trim().to_string();

    git(&["checkout", "-qb", "replay", "HEAD~1"]);
    let cp = git(&["-c", "user.email=real@gmail.com", "cherry-pick", &sha]);
    assert!(cp.status.success(), "cherry-pick itself failed: {}", out_text(&cp));
    assert!(
        !String::from_utf8_lossy(&cp.stderr).contains("commit-identity guard"),
        "pre-commit ran on a cherry-pick, invalidating this test's premise: {}",
        out_text(&cp)
    );

    let bad = git(&["push", "origin", "HEAD:refs/heads/replay"]);
    assert!(!bad.status.success(), "a replayed foreign-email commit was pushed: {}", out_text(&bad));
    assert!(
        String::from_utf8_lossy(&bad.stderr).contains("commit-identity guard (pre-push)"),
        "refusal did not name itself: {}",
        out_text(&bad)
    );

    assert!(git(&["commit", "-q", "--amend", "--reset-author", "--no-edit"]).status.success());
    let good = git(&["push", "origin", "HEAD:refs/heads/replay"]);
    assert!(good.status.success(), "the fixed-up identity was still refused: {}", out_text(&good));
}

/// The buffered wrapper's `mktemp` file must not leak: an earlier draft
/// `exec`'d the guard as the wrapper's last step, which replaces the shell
/// image and skips the `trap ... EXIT` cleaning the buffer up — every
/// successful push would leave one file behind in `$TMPDIR` (review finding
/// on #1006, post-verification). Runs several pushes through a `$TMPDIR` of
/// its own and asserts it holds no stray files once they're done.
#[test]
fn a_successful_push_leaves_no_stray_stdin_buffer_file_behind() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "dispatch failed: {}", out_text(&out));

    let scratch_tmpdir = f.tmp.path().join("push-tmpdir");
    std::fs::create_dir_all(&scratch_tmpdir).unwrap();

    let wt = repo.join(".claude/worktrees/implement-395");
    let git = |args: &[&str]| {
        std::process::Command::new("git").arg("-C").arg(&wt).args(args).env("TMPDIR", &scratch_tmpdir).output().unwrap()
    };
    for i in 0..3 {
        std::fs::write(wt.join(format!("g{i}")), "x\n").unwrap();
        git(&["add", &format!("g{i}")]);
        assert!(git(&["commit", "-qm", &format!("x{i}")]).status.success());
        let push = git(&["push", "origin", &format!("HEAD:refs/heads/push{i}")]);
        assert!(push.status.success(), "push {i} failed: {}", out_text(&push));
    }

    let leftover: Vec<_> = std::fs::read_dir(&scratch_tmpdir).unwrap().filter_map(|e| e.ok()).map(|e| e.file_name()).collect();
    assert!(leftover.is_empty(), "the pre-push wrapper's stdin buffer leaked: {leftover:?}");
}

/// The wrapper's buffering `cat >"$stdin_buf"` ignored its own exit status
/// (Codex gate finding on #1006, PR #1068): a copy that fails partway —
/// disk full, an I/O error — after writing one or more complete ref lines
/// hands both the foreign hook and the guard a truncated-but-nonempty ref
/// list, so the guard's zero-ref refusal never fires and the ref that got
/// cut off pushes through unchecked. Simulated here with a stub `cat` ahead
/// on PATH that writes one line then exits 1 — the wrapper must refuse
/// before either the foreign hook or the guard ever runs, which a marker
/// file from each proves.
#[test]
fn a_failed_stdin_buffer_copy_refuses_before_either_hook_runs() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let foreign_ran = f.tmp.path().join("foreign-ran");
    let guard_ran = f.tmp.path().join("guard-ran");
    let hook = hooks_dir(&repo).join("pre-push");
    let foreign = format!("#!/bin/sh\n: >{}\nexit 0\n", foreign_ran.display());
    std::fs::write(&hook, &foreign).unwrap();

    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "dispatch failed: {}", out_text(&out));

    // A guard-ran marker is written by wrapping the installed guard binary
    // itself, since the guard script's own content isn't ours to edit for a
    // test — a thin stub ahead on PATH under the guard's own name would not
    // be reached (the wrapper execs it by absolute path). Instead: rename
    // the installed guard aside and put a marker-writing stand-in at its
    // exact path, since that's the one thing the failed copy must never
    // reach regardless of how it's implemented.
    let guard_path = hooks_dir(&repo).join("commit-identity-guard-pre-push");
    std::fs::write(&guard_path, format!("#!/bin/sh\n: >{}\nexit 0\n", guard_ran.display())).unwrap();
    let mut perms = std::fs::metadata(&guard_path).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
    std::fs::set_permissions(&guard_path, perms).unwrap();

    let stub_bin = f.tmp.path().join("stub-bin");
    std::fs::create_dir_all(&stub_bin).unwrap();
    let stub_cat = stub_bin.join("cat");
    std::fs::write(&stub_cat, "#!/bin/sh\necho refs/heads/main\nexit 1\n").unwrap();
    let mut perms = std::fs::metadata(&stub_cat).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
    std::fs::set_permissions(&stub_cat, perms).unwrap();
    let real_path = std::env::var("PATH").unwrap_or_default();
    let stubbed_path = format!("{}:{real_path}", stub_bin.display());

    let wt = repo.join(".claude/worktrees/implement-395");
    std::fs::write(wt.join("g"), "x\n").unwrap();
    std::process::Command::new("git").arg("-C").arg(&wt).args(["add", "g"]).output().unwrap();
    assert!(std::process::Command::new("git").arg("-C").arg(&wt).args(["commit", "-qm", "x"]).output().unwrap().status.success());
    let push = std::process::Command::new("git")
        .arg("-C")
        .arg(&wt)
        .args(["push", "origin", "HEAD:refs/heads/stub"])
        .env("PATH", &stubbed_path)
        .output()
        .unwrap();
    assert!(!push.status.success(), "a push whose stdin buffer copy failed was not refused: {}", out_text(&push));
    assert!(
        String::from_utf8_lossy(&push.stderr).contains("could not buffer the pre-push ref list"),
        "refused for a reason other than the failed copy: {}",
        out_text(&push)
    );
    assert!(!foreign_ran.exists(), "the foreign hook ran despite the buffering copy having failed");
    assert!(!guard_ran.exists(), "the guard ran despite the buffering copy having failed");
}

/// `COMMIT_IDENTITY_OVERRIDE` is the one legitimate way past the guard, same
/// escape as the pre-commit half, and it must reach the push side too.
#[test]
fn the_pre_push_guard_override_escape_lets_a_foreign_email_push_through() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "dispatch failed: {}", out_text(&out));

    let wt = repo.join(".claude/worktrees/implement-395");
    let git = |args: &[&str]| std::process::Command::new("git").arg("-C").arg(&wt).args(args).output().unwrap();
    std::fs::write(wt.join("g"), "x\n").unwrap();
    git(&["add", "g"]);
    assert!(git(&["commit", "-qm", "x"]).status.success());
    let sha = String::from_utf8(git(&["rev-parse", "HEAD"]).stdout).unwrap().trim().to_string();
    git(&["checkout", "-qb", "replay", "HEAD~1"]);
    assert!(git(&["-c", "user.email=real@gmail.com", "cherry-pick", &sha]).status.success());

    let push = std::process::Command::new("git")
        .arg("-C")
        .arg(&wt)
        .args(["push", "origin", "HEAD:refs/heads/replay"])
        .env("COMMIT_IDENTITY_OVERRIDE", "release bot")
        .output()
        .unwrap();
    assert!(push.status.success(), "override did not let the push through: {}", out_text(&push));
    assert!(String::from_utf8_lossy(&push.stderr).contains("release bot"), "override did not name its reason: {}", out_text(&push));
}

/// Whatever real pre-push hook a repo already had (tests, a size check) is
/// preserved and still runs, same guarantee #1009 gives the pre-commit slot
/// — and, unlike a foreign hook that merely `exit 0`s without touching
/// stdin, this one actually reads and discards the ref list the way a real
/// pre-push hook typically does (a `while read` loop over stdin, same shape
/// as `git`'s own `pre-push.sample`). A foreign hook that drains stdin
/// before the guard gets a turn is exactly what starves the guard's own
/// `while read` and lets it exit 0 having checked nothing (#1006 review
/// finding C1/S1) — this is the regression test for the stdin-buffering fix
/// that closes that hole, run through a real dispatch-installed wrapper
/// rather than the guard script called directly.
#[test]
fn a_foreign_pre_push_hook_is_preserved_and_the_guard_still_refuses_a_replayed_commit() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-push");
    let foreign = "#!/bin/sh\nwhile read -r a b c d; do :; done\nexit 0\n";
    std::fs::write(&hook, foreign).unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "dispatch refused over a foreign pre-push hook: {}", out_text(&out));

    let moved_aside = hooks_dir(&repo).join("pre-push.foreign");
    assert_eq!(std::fs::read_to_string(&moved_aside).unwrap(), foreign, "the foreign pre-push hook was not preserved");

    let wt = repo.join(".claude/worktrees/implement-395");
    let git = |args: &[&str]| std::process::Command::new("git").arg("-C").arg(&wt).args(args).output().unwrap();
    std::fs::write(wt.join("g"), "x\n").unwrap();
    git(&["add", "g"]);
    assert!(git(&["commit", "-qm", "x"]).status.success());
    let sha = String::from_utf8(git(&["rev-parse", "HEAD"]).stdout).unwrap().trim().to_string();
    git(&["checkout", "-qb", "replay", "HEAD~1"]);
    assert!(git(&["-c", "user.email=real@gmail.com", "cherry-pick", &sha]).status.success());
    let bad = git(&["push", "origin", "HEAD:refs/heads/replay"]);
    assert!(!bad.status.success(), "a replayed foreign-email commit was pushed over a taken-over foreign hook: {}", out_text(&bad));
    let bad_err = String::from_utf8_lossy(&bad.stderr);
    assert!(bad_err.contains("commit-identity guard (pre-push)"), "{bad_err}");
    // Names the actual mismatched email, not just "no ref updates were read"
    // (the zero-refs fallback) — proves the guard actually enumerated the
    // pushed commit through the stdin-draining foreign hook, rather than
    // merely refusing everything a foreign hook happens to consume stdin
    // from (which would be an availability bug of its own, not a fix).
    assert!(bad_err.contains("real@gmail.com"), "refused for a reason other than the mismatched email: {bad_err}");

    // A correctly-configured push through the same stdin-draining foreign
    // hook must still succeed — the buffering fix, not just a blanket
    // "stdin exhausted, refuse" fallback.
    git(&["checkout", "-q", "implement-395"]);
    git(&["branch", "-qD", "replay"]);
    std::fs::write(wt.join("h"), "y\n").unwrap();
    git(&["add", "h"]);
    assert!(git(&["commit", "-qm", "y"]).status.success());
    let good = git(&["push", "origin", "HEAD:refs/heads/good"]);
    assert!(good.status.success(), "a correctly-configured push was refused through a stdin-draining foreign hook: {}", out_text(&good));
}

/// Commits a foreign-email change in the dispatched worktree for ticket `n`
/// and asserts the guard still refuses it while a correctly-configured
/// commit still succeeds — the end-to-end proof that whatever foreign hook
/// was in place before dispatch, the guard runs regardless (#1009).
fn refuses_a_foreign_email_commit(repo: &std::path::Path, n: &str) {
    let wt = repo.join(".claude/worktrees").join(format!("implement-{n}"));
    std::fs::write(wt.join("g"), "x\n").unwrap();
    let git = |args: &[&str]| std::process::Command::new("git").arg("-C").arg(&wt).args(args).output().unwrap();
    git(&["add", "g"]);
    let bad = git(&["-c", "user.email=real@gmail.com", "commit", "-qm", "x"]);
    assert!(!bad.status.success(), "a foreign email committed: {}", out_text(&bad));
    assert!(
        String::from_utf8_lossy(&bad.stderr).contains("commit-identity guard"),
        "refused for a reason other than the guard: {}",
        out_text(&bad)
    );
    let good = git(&["commit", "-qm", "x"]);
    assert!(good.status.success(), "configured identity refused: {}", out_text(&good));
}

/// A foreign hook that neither names the guard nor calls it: the pre-#1009
/// text-match check would have refused dispatch entirely over this one.
/// Taking ownership means dispatch proceeds and the guard runs anyway.
#[test]
fn a_foreign_hook_with_no_guard_reference_is_taken_over_and_still_refuses_a_foreign_email_commit() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    std::fs::write(&hook, "#!/bin/sh\nexit 0\n").unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "dispatch refused over a foreign hook: {}", out_text(&out));
    refuses_a_foreign_email_commit(&repo, "395");
}

/// A hook that echoes the guard's name on a non-comment line without ever
/// invoking it — exactly what the old `invokes_guard` text match would have
/// accepted as proof the guard ran.
#[test]
fn a_spoofed_hook_that_only_echoes_the_guards_name_still_refuses_a_foreign_email_commit() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    std::fs::write(&hook, "#!/bin/sh\necho commit-identity-guard\nexit 0\n").unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    refuses_a_foreign_email_commit(&repo, "395");
}

/// A hook that does call the guard, then swallows its exit code with
/// `|| true` — the old text match saw the call and never noticed the
/// suppression.
#[test]
fn a_hook_that_calls_the_guard_then_swallows_its_failure_still_refuses() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    std::fs::write(&hook, "#!/bin/sh\n\"$(dirname \"$0\")/commit-identity-guard\" || true\n").unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    refuses_a_foreign_email_commit(&repo, "395");
}

/// A foreign hook with no executable bit — git would never have run it at
/// all, and the pre-#1009 accepted-hook path never checked for this either.
/// Taking ownership forces it, and the final `pre-commit`, executable.
#[test]
fn a_non_executable_foreign_hook_is_taken_over_and_still_refuses_a_foreign_email_commit() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    std::fs::write(&hook, "#!/bin/sh\nexit 0\n").unwrap();
    let mut perms = std::fs::metadata(&hook).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o644);
    std::fs::set_permissions(&hook, perms).unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let installed = std::fs::metadata(&hook).unwrap().permissions();
    assert!(std::os::unix::fs::PermissionsExt::mode(&installed) & 0o111 != 0, "installed pre-commit is not executable");
    refuses_a_foreign_email_commit(&repo, "395");
}

/// Ownership is taken once: the foreign hook is moved aside under a stable
/// name on the first dispatch, and a second dispatch — the wrapper already
/// in place — leaves both files alone.
#[test]
fn a_foreign_hook_is_moved_aside_once_then_left_alone_on_a_second_dispatch() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    let foreign_text = "#!/bin/sh\necho foreign-check\n\"$(dirname \"$0\")/commit-identity-guard\" || exit 1\n";
    std::fs::write(&hook, foreign_text).unwrap();
    let out1 = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out1.status.success(), "{}", out_text(&out1));
    let moved_aside = hooks_dir(&repo).join("pre-commit.foreign");
    assert_eq!(std::fs::read_to_string(&moved_aside).unwrap(), foreign_text);
    let wrapper_after_first = std::fs::read_to_string(&hook).unwrap();
    assert_ne!(wrapper_after_first, foreign_text, "the foreign hook was left in place as pre-commit instead of moved aside");

    let out2 = f.dispatch(&["--repo", repo.to_str().unwrap(), "396"], &default_scenario());
    assert!(out2.status.success(), "{}", out_text(&out2));
    assert_eq!(std::fs::read_to_string(&hook).unwrap(), wrapper_after_first, "wrapper rewritten on a second dispatch");
    assert_eq!(std::fs::read_to_string(&moved_aside).unwrap(), foreign_text, "moved-aside hook touched on a second dispatch");
}

/// A stale version of the lane's own wrapper — the same comment a real
/// wrapper carries, but not byte-identical to the wrapper text this build
/// installs, exactly as a wrapper written by an earlier build of the lane
/// would read. Ownership is byte-identity only, so this is foreign like any
/// other hook: displaced to `pre-commit.foreign` and run by the fresh
/// wrapper before the guard — harmless, since its own body is the pre-#1009
/// two-line form (`exec .../commit-identity-guard`), not self-referential.
/// The guard still runs and still refuses a foreign-email commit.
#[test]
fn a_stale_lane_wrapper_with_different_bytes_is_displaced_like_any_foreign_hook_and_the_guard_still_runs() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    let stale = "#!/bin/sh\n# lane commit-identity guard wrapper (#934)\nexec \"$(dirname \"$0\")/commit-identity-guard\"\n";
    std::fs::write(&hook, stale).unwrap();
    let mut perms = std::fs::metadata(&hook).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
    std::fs::set_permissions(&hook, perms).unwrap();

    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    let moved_aside = hooks_dir(&repo).join("pre-commit.foreign");
    assert_eq!(std::fs::read_to_string(&moved_aside).unwrap(), stale, "a stale lane wrapper was not displaced");
    assert_ne!(std::fs::read_to_string(&hook).unwrap(), stale, "the stale wrapper was left in place instead of replaced");
    refuses_a_foreign_email_commit(&repo, "395");
}

/// A foreign hook that carries the exact comment phrase a real lane wrapper
/// uses — "lane commit-identity guard wrapper" — without being byte-identical
/// to the current wrapper, and without actually invoking the guard: the
/// spoof a marker-based (or any other source-text) ownership check would
/// have fallen for, skipping the takeover entirely and leaving the guard
/// never installed (the hole #1009 exists to close; caught on the Codex gate
/// for PR #1053). Byte-identity means this is foreign like any other hook.
#[test]
fn a_hook_that_spoofs_the_wrapper_comment_is_still_taken_over_and_the_guard_still_runs() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    let spoofed = "#!/bin/sh\n# lane commit-identity guard wrapper — nothing else here\nexit 0\n";
    std::fs::write(&hook, spoofed).unwrap();
    let mut perms = std::fs::metadata(&hook).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
    std::fs::set_permissions(&hook, perms).unwrap();

    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    let moved_aside = hooks_dir(&repo).join("pre-commit.foreign");
    assert_eq!(std::fs::read_to_string(&moved_aside).unwrap(), spoofed, "a marker-spoofing hook was not taken over");
    refuses_a_foreign_email_commit(&repo, "395");
}

/// The same spoof, but with no executable bit — the exec-bit path (#1009's
/// third named scenario) intersecting the marker spoof (found on the same
/// Codex gate). Must still end up guarded.
#[test]
fn a_non_executable_hook_that_spoofs_the_wrapper_comment_is_still_taken_over_and_the_guard_still_runs() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    let spoofed = "#!/bin/sh\n# lane commit-identity guard wrapper — nothing else here\nexit 0\n";
    std::fs::write(&hook, spoofed).unwrap();
    let mut perms = std::fs::metadata(&hook).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o644);
    std::fs::set_permissions(&hook, perms).unwrap();

    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    let moved_aside = hooks_dir(&repo).join("pre-commit.foreign");
    assert_eq!(std::fs::read_to_string(&moved_aside).unwrap(), spoofed, "a non-executable marker-spoofing hook was not taken over");
    let installed = std::fs::metadata(&hook).unwrap().permissions();
    assert!(std::os::unix::fs::PermissionsExt::mode(&installed) & 0o111 != 0, "installed pre-commit is not executable");
    refuses_a_foreign_email_commit(&repo, "395");
}

/// `pre-commit.foreign` already holds a hook from an earlier takeover; a
/// second, different hook has since been installed as `pre-commit` (husky, a
/// setup script, a hand edit). Overwriting the slot would destroy the first
/// preserved hook with no record (#1009 C3) — refuse instead.
#[test]
fn a_pre_commit_foreign_already_holding_a_different_hook_refuses_dispatch() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let hook = hooks_dir(&repo).join("pre-commit");
    let foreign_slot = hooks_dir(&repo).join("pre-commit.foreign");
    std::fs::write(&foreign_slot, "#!/bin/sh\necho old-foreign\nexit 0\n").unwrap();
    std::fs::write(&hook, "#!/bin/sh\necho new-foreign\nexit 0\n").unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &default_scenario());
    assert!(!out.status.success(), "dispatch went ahead over a foreign-slot collision");
    assert!(out_text(&out).contains("pre-commit.foreign"), "{}", out_text(&out));
    assert_eq!(std::fs::read_to_string(&foreign_slot).unwrap(), "#!/bin/sh\necho old-foreign\nexit 0\n", "existing foreign hook clobbered");
    assert!(!repo.join(".claude/worktrees/implement-395").exists());
}

/// Rewrites the stand-in controller's registry record with a sessionId, so a
/// herdr agent's `agent_session.value` can name it.
fn give_controller_a_session_id(f: &Fixture, id: &str) {
    let pid = std::process::id() as i32;
    let stat = lane::proc_info::read_stat(pid).unwrap();
    std::fs::write(
        f.session_file(),
        format!(r#"{{"pid":{pid},"sessionId":"{id}","procStart":"{}","name":"skills-ctl"}}"#, stat.start),
    )
    .unwrap();
}

#[test]
fn a_derived_controller_that_is_a_named_herdr_agent_is_briefed_by_that_name() {
    let f = Fixture::new();
    f.reset_home(true);
    give_controller_a_session_id(&f, "sid-ctl");
    f.set_agents(r#"[{"name":"skills-dc","agent_session":{"value":"sid-ctl"}},{"agent_session":{"value":"sid-other"}}]"#);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "410"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(
        f.calls().lines().any(|l| l
            == "herdr agent prompt sudokumaker-custom-constrain-410 /implement 410 --tier heavy --controller \"skills-dc\" --wait --until working --timeout 120000"),
        "{}",
        f.calls()
    );
}

#[test]
fn a_controller_whose_herdr_agent_is_unnamed_keeps_its_session_name() {
    let f = Fixture::new();
    f.reset_home(true);
    give_controller_a_session_id(&f, "sid-ctl");
    f.set_agents(r#"[{"agent":"claude","agent_session":{"value":"sid-ctl"}}]"#);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "411"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(f.calls().contains("--controller \"skills-ctl\""), "{}", f.calls());
}

#[test]
fn a_failed_agent_listing_refuses_instead_of_briefing_the_session_name() {
    let f = Fixture::new();
    f.reset_home(true);
    give_controller_a_session_id(&f, "sid-ctl");
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("HERDR_LIST_FAIL", "true")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "412"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "412", "herdr agent list"), "{}", out_text(&out));
    assert!(!f.calls().contains("herdr agent prompt"), "{}", f.calls());
}

#[test]
fn a_herdr_agent_name_holding_a_double_quote_is_refused_not_dropped() {
    let f = Fixture::new();
    f.reset_home(true);
    give_controller_a_session_id(&f, "sid-ctl");
    f.set_agents(r#"[{"name":"say \"hi\"","agent_session":{"value":"sid-ctl"}}]"#);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "413"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "413", "double quote"), "{}", out_text(&out));
}

#[test]
fn a_controller_record_with_no_session_id_refuses_even_when_a_named_agent_exists() {
    let f = Fixture::new();
    f.reset_home(true);
    let pid = std::process::id() as i32;
    let stat = lane::proc_info::read_stat(pid).unwrap();
    std::fs::write(
        f.session_file(),
        format!(r#"{{"pid":{pid},"procStart":"{}","name":"skills-ctl"}}"#, stat.start),
    )
    .unwrap();
    f.set_agents(r#"[{"name":"skills-dc","agent_session":{"value":"sid-ctl"}}]"#);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "414"], &default_scenario());
    assert!(refused(&out, &f.calls(), &repo, "414", "no sessionId"), "{}", out_text(&out));
    assert!(!f.calls().contains("herdr agent prompt"), "{}", f.calls());
}

// --- #964: dispatch records the controller/worker pair for /clear to restore ---

fn workers_file(f: &Fixture) -> std::path::PathBuf {
    f.home().join(".claude/sessions").join(format!("{}.workers.jsonl", std::process::id()))
}

#[test]
fn a_dispatch_appends_a_worker_record_for_the_controllers_own_session() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let wt = repo.join(".claude/worktrees/implement-415");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "415"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    let records = lane::workers::read(&f.home(), &std::process::id().to_string());
    assert_eq!(records.len(), 1, "{records:?}");
    let r = &records[0];
    assert_eq!(r.agent, "sudokumaker-custom-constrain-415");
    assert_eq!(r.tickets, vec!["415".to_string()]);
    assert_eq!(r.branch, "implement-415");
    assert_eq!(r.workspace, wt.display().to_string());
    assert_eq!(r.repo, "caneff/sudokumaker-custom-constraints");
    assert_eq!(r.cleanup, format!("cd {} && merge-cleanup implement-415 --repo {}", repo.display(), repo.display()));
    assert!(!r.chris_merges);
    assert!(!r.dispatched_at.is_empty(), "dispatched_at should be stamped");
    assert_eq!(r.proc_start, f.own_proc_start(), "#964 fix round 1: the record must carry the controller session's own starttime");
}

/// #1087: the record's `workspace` is `canonical_workspace_path`'s output,
/// not the raw spelling of the path dispatch built. `primary` comes from git
/// and is already real, so the raw spelling differs only when a component
/// below it is a symlink: `.claude` here. Only a dispatch that calls the
/// helper writes the resolved path.
#[test]
fn a_dispatch_through_a_symlinked_claude_dir_records_the_canonical_workspace() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let real_claude = repo.parent().unwrap().join("real-claude");
    std::fs::create_dir_all(real_claude.join("worktrees")).unwrap();
    std::os::unix::fs::symlink(&real_claude, repo.join(".claude")).unwrap();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "415"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));

    let records = lane::workers::read(&f.home(), &std::process::id().to_string());
    assert_eq!(records.len(), 1, "{records:?}");
    let raw = repo.join(".claude/worktrees/implement-415");
    let canonical = real_claude.canonicalize().unwrap().join("worktrees/implement-415");
    assert_ne!(raw, canonical, "the raw spelling must differ for this test to mean anything");
    assert_eq!(records[0].workspace, canonical.display().to_string());
}

#[test]
fn a_clumps_worker_record_carries_every_ticket_lowest_first() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "420", "416"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let records = lane::workers::read(&f.home(), &std::process::id().to_string());
    assert_eq!(records.len(), 1);
    assert_eq!(records[0].tickets, vec!["416".to_string(), "420".to_string()]);
    assert_eq!(records[0].branch, "implement-416");
}

#[test]
fn a_ready_for_human_worker_records_chris_merges() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "ready-for-human")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "417"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    let records = lane::workers::read(&f.home(), &std::process::id().to_string());
    assert_eq!(records.len(), 1);
    assert!(records[0].chris_merges);
}

#[test]
fn two_dispatches_from_one_controller_append_two_records() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    assert!(f.dispatch(&["--repo", repo.to_str().unwrap(), "418"], &default_scenario()).status.success());
    assert!(f.dispatch(&["--repo", repo.to_str().unwrap(), "419"], &default_scenario()).status.success());
    let records = lane::workers::read(&f.home(), &std::process::id().to_string());
    assert_eq!(records.len(), 2, "{records:?}");
    assert_eq!(records[0].branch, "implement-418");
    assert_eq!(records[1].branch, "implement-419");
}

#[test]
fn an_explicit_controller_flag_resolved_only_through_the_herdr_hop_still_gets_a_record() {
    let f = Fixture::new();
    f.reset_home(true);
    // The flag ("skills-dc") is neither the live session's own name
    // ("skills-ctl", from reset_home) nor its sessionId directly — only
    // herdr's agent_session.value ties it back to the live session
    // (sid-test, the fixture's fixed sessionId) that resolve_controller_pid
    // must still find.
    f.set_agents(r#"[{"name":"skills-dc","agent_session":{"value":"sid-test"}}]"#);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--controller", "skills-dc", "421"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let records = lane::workers::read(&f.home(), &std::process::id().to_string());
    assert_eq!(records.len(), 1, "{records:?}");
    assert_eq!(records[0].branch, "implement-421");
}

#[test]
fn a_controller_that_resolves_to_no_live_session_dispatches_with_no_record_and_no_failure() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    // Names no live session and no herdr agent: the dispatch still succeeds
    // (the brief only needs a string to print), but nothing can be resolved
    // to a pid, so no record is written and nothing panics over it.
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--controller", "nobody-home", "422"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(!workers_file(&f).exists(), "no controller record file should be created");
}

/// Installs a `git` on `f`'s scratch PATH, ahead of the real one, that hangs
/// forever on `fetch` and delegates every other subcommand to the real git —
/// so the claim lock's own git calls (rev-parse, worktree list, branch
/// checks) still work and only the fetch stalls (#976).
fn install_hanging_fetch_git(f: &Fixture) {
    let real_git = which("git");
    let script = format!(
        "#!/bin/sh\nfor a in \"$@\"; do\n  if [ \"$a\" = fetch ]; then\n    sleep 30\n    exit 1\n  fi\ndone\nexec {} \"$@\"\n",
        real_git.display()
    );
    let path = f.tmp.path().join("bin/git");
    std::fs::write(&path, script).unwrap();
    let mut perms = std::fs::metadata(&path).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
    std::fs::set_permissions(&path, perms).unwrap();
}

#[test]
fn a_stalled_fetch_fails_fast_under_the_bound_instead_of_pinning_the_claim_lock() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    install_hanging_fetch_git(&f);
    let scenario = with(&default_scenario(), &[("LANE_FETCH_TIMEOUT_MS", "200")]);
    let start = std::time::Instant::now();
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "395"], &scenario);
    assert!(start.elapsed() < std::time::Duration::from_secs(5), "waited {:?} past a 200ms fetch bound", start.elapsed());
    assert!(refused(&out, &f.calls(), &repo, "395", "git fetch"), "{}", out_text(&out));
}

#[test]
fn a_documentation_label_on_a_ticket_targeting_a_skill_body_dispatches_heavy_and_strips_it() {
    // #969: the filer's hand-put `documentation` label sent a `SKILL.md`
    // change out at light tier, and the worker pushed it straight to main.
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(
        &default_scenario(),
        &[
            ("GH_LABELS", "documentation,ready-for-agent"),
            ("GH_BODY", "Reword the step in `multi-axis-code-review/SKILL.md` § 6."),
        ],
    );
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "403"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    let calls = f.calls();
    assert!(calls.contains("/implement 403 --tier heavy"), "{calls}");
    assert!(!calls.contains("--tier light"), "{calls}");
    assert!(
        calls.lines().any(|l| l
            == format!("gh issue edit 403 --repo {SLUG} --remove-label ready-for-agent --remove-label documentation --add-label in-progress --add-assignee @me")),
        "{calls}"
    );
    let text = out_text(&out);
    assert!(text.contains("documentation label stripped") && text.contains("multi-axis-code-review/SKILL.md"), "{text}");
}

#[test]
fn a_documentation_ticket_naming_only_prose_stays_light_and_keeps_its_label() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(
        &default_scenario(),
        &[("GH_LABELS", "documentation,ready-for-agent"), ("GH_BODY", "Add `docs/research/note.md` and update AGENTS.md.")],
    );
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "403"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(f.calls().contains("/implement 403 --tier light"), "{}", f.calls());
    assert!(!f.calls().contains("--remove-label documentation"), "{}", f.calls());
}

#[test]
fn an_unreadable_body_dispatches_heavy_and_keeps_the_documentation_label() {
    // Class 1: a failed read must not pass for "names no code", and it is no
    // evidence the label was wrong, so it is not removed either.
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "documentation,ready-for-agent"), ("GH_BODY_FAIL_403", "1")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "403"], &scenario);
    assert!(out.status.success(), "{}", out_text(&out));
    let calls = f.calls();
    assert!(calls.contains("/implement 403 --tier heavy"), "{calls}");
    assert!(!calls.contains("--remove-label documentation"), "{calls}");
    assert!(out_text(&out).contains("body unreadable, dispatched heavy: #403"), "{}", out_text(&out));
}

// --- #1146: a burn's run id reaches the brief ---------------------------------

#[test]
fn a_run_id_is_carried_in_the_brief_so_the_worker_knows_a_run_file_is_under_it() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--run", "burn-2026-09-23-0700", "412"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    assert_eq!(
        prompt_line(&f),
        "herdr agent prompt sudokumaker-custom-constrain-412 /implement 412 --tier heavy --controller \"skills-ctl\" --run burn-2026-09-23-0700 --wait --until working --timeout 120000"
    );
    assert!(out_text(&out).contains("dispatched #412 (sonnet, heavy tier, run burn-2026-09-23-0700, controller skills-ctl)"), "{}", out_text(&out));
}

#[test]
fn a_run_id_outside_the_run_file_grammar_is_refused_before_the_claim() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    // runfile.py's own run-id grammar: a space or quote would split the
    // one-line brief, a `/` or `..` names no run file, empty names none.
    for bad in ["burn x", "burn\"x", "../burn", "-burn", ".burn", "", "burn\n"] {
        let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--run", bad, "413"], &default_scenario());
        assert!(refused(&out, &f.calls(), &repo, "413", "run id"), "--run {bad:?}: {}", out_text(&out));
    }
}

#[test]
fn a_run_id_on_a_spec_dispatch_is_refused() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--run", "burn-2026-09-23-0700", "--spec", "395"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "--run"), "{}", out_text(&out));
}

#[test]
fn a_clumps_run_id_sits_before_the_clump_note() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--run", "burn-2026-09-23-0700", "424", "423"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let line = prompt_line(&f);
    assert!(
        line.starts_with("herdr agent prompt sudokumaker-custom-constrain-423 /implement 423 424 --tier heavy --controller \"skills-ctl\" --run burn-2026-09-23-0700 -- Clump:"),
        "{line}"
    );
}

#[test]
fn help_documents_the_run_flag() {
    let f = Fixture::new();
    let out = f.dispatch(&["--help"], &default_scenario());
    assert!(out.status.success(), "{}", out_text(&out));
    let text = out_text(&out);
    for want in ["[--run <run-id>]", "--run <run-id>", "no run file"] {
        assert!(text.contains(want), "help lacks {want:?}:\n{text}");
    }
}
