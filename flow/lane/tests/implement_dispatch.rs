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
fn spec_mode_without_slots_is_refused() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let scenario = with(&default_scenario(), &[("GH_LABELS", "spec,ready-for-agent")]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "--spec", "395"], &scenario);
    assert!(refused(&out, &f.calls(), &repo, "395", "--slots"), "{}", out_text(&out));
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
        "--spec <n> --slots <k>",
        "/implement-spec <n> --slots <k>",
        "spec-<n>",
        "ready-for-human",
        "--chris-merges",
        "Several issue numbers are one clump",
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
    assert!(
        f.calls().lines().any(|l| l
            == "herdr agent prompt sudokumaker-custom-constrain-423 /implement 423 424 --tier heavy --controller \"skills-ctl\" --wait --until working --timeout 120000"),
        "{}",
        f.calls()
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
fn a_clump_is_light_only_when_every_ticket_is_documentation() {
    let f = Fixture::new();
    f.reset_home(true);
    let repo = f.mkfixture("sudokumaker-custom-constraints", "main");
    let docs = "OPEN\tdocumentation,ready-for-agent\t";
    let all_docs = with(&default_scenario(), &[("GH_ISSUE_431", docs), ("GH_ISSUE_432", docs)]);
    let out = f.dispatch(&["--repo", repo.to_str().unwrap(), "431", "432"], &all_docs);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(f.calls().contains("/implement 431 432 --tier light"), "{}", f.calls());

    let f2 = Fixture::new();
    f2.reset_home(true);
    let repo2 = f2.mkfixture("sudokumaker-custom-constraints", "main");
    // One ticket's diff is code, so the clump's single diff is code.
    let mixed = with(&default_scenario(), &[("GH_ISSUE_433", docs)]);
    let out2 = f2.dispatch(&["--repo", repo2.to_str().unwrap(), "433", "434"], &mixed);
    assert!(out2.status.success(), "{}", out_text(&out2));
    assert!(f2.calls().contains("/implement 433 434 --tier heavy"), "{}", f2.calls());
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
