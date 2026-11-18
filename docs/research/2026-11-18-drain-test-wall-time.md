# drain/drain_test.py wall time: cause and fix (#1954)

Measured 2026-11-18 on this box (WSL, 32 cores, shared with other workers).

## Cause: code, not load

`implement-spec/frontier.py` gained `SETTLE_SECONDS = 3.0` on 2026-11-16 (#1913,
commit 356c5bec): `settled_listing` reads the queue twice with a 3 s sleep
between. `drain.py` reads the frontier on every `--once` / anchor path, several
times per case (`read_frontier`, `next_anchor`), so nearly every drain case paid
about 3 s per read. That is the date the seam went from 3.4–5 min to 16–21 min.

Evidence:

- Before the fix, one case run alone (`-k test_anchor_may_name_a_spec`): 10.1 s
  wall, 1.2 s user, 0.5 s sys. Load 18, so load did not make it slow.
- `faulthandler.dump_traceback_later(5)` in the `drain.py` child of that case
  showed it inside `frontier.py:532` (`time.sleep(SETTLE_SECONDS)`) via
  `drain.py:287 read_frontier` -> `read_queue` -> `frontier`.
- Whole file, before: 179 passed in 1048 s wall (17m29s), 138 s user+sys.
  Per-test calls cluster at 7–19 s for ~100 cases; the sum of call times is the
  wall time, so the time was waits and not work.
- Whole file, after the fix: 179 passed in 185 s wall (3m06s), 148 s user+sys.
  Load average at start: 14.06 before, 20.29 after, so the after figure is not
  a quiet-box best case.

Load made it worse (the box ran at 14–20 throughout) but did not cause it: the
sleep is a fixed 3 s per read whatever the load.

## Fix

`SETTLE_SECONDS` reads `FRONTIER_SETTLE_SECONDS` (default 3.0, unchanged in
production). `drain_test.py`'s `drain_env` sets it to 0.05, as it already does
for `DRAIN_POLL_SECONDS` and `DRAIN_FRONTIER_RETRY_SECONDS`. No assertion was
removed or loosened; `implement-spec/frontier_test.py` still sets it to 3.0 where
it tests the pause itself.

## Per-test durations

Slowest 12 calls, before (`pytest --durations=0`, load 14.06 15.89 16.24 at start):

    18.59s call     drain/drain_test.py::test_an_anchor_note_that_names_another_ticket_or_is_malformed_is_not_resumed
    17.05s call     drain/drain_test.py::test_the_lowest_numbered_unit_goes_first_whether_a_ticket_or_a_spec
    13.82s call     drain/drain_test.py::test_anchor_starts_the_bundle_from_that_ticket_and_only_the_first
    13.71s call     drain/drain_test.py::test_a_chooser_that_fails_or_says_nothing_usable_bundles_the_anchor_alone
    10.71s call     drain/drain_test.py::test_a_ticket_failing_twice_is_handed_over_and_the_loop_moves_on
    10.60s call     drain/drain_test.py::test_each_merge_runs_the_per_change_command_and_no_run_follows_the_last_bundle
    10.29s call     drain/drain_test.py::test_a_ready_slice_is_never_the_anchor_and_never_joins_a_bundle
    10.11s call     drain/drain_test.py::test_blocked_and_claimed_and_human_tickets_are_skipped
    10.04s call     drain/drain_test.py::test_a_ticket_whose_workspace_is_kept_is_not_picked_and_an_anchor_naming_it_is_refused
    10.03s call     drain/drain_test.py::test_an_anchor_this_run_ended_is_not_resumed_even_when_its_reread_is_stale
    10.02s call     drain/drain_test.py::test_a_merged_ticket_the_open_list_still_carries_is_not_resumed
    9.94s call     drain/drain_test.py::test_a_ticket_taken_since_the_pick_is_not_claimed_over

Slowest 12 calls, after (load 20.29 17.39 16.52 at start):

    6.24s call     drain/drain_test.py::test_once_drains_a_ticket_through_the_in_memory_tracker_with_no_gh
    3.14s call     drain/drain_test.py::test_a_herdr_that_hangs_stops_the_drain_naming_herdr
    3.08s call     drain/drain_test.py::test_two_bundles_in_a_row_handed_over_stop_the_loop
    3.05s call     drain/drain_test.py::test_a_ticket_failing_twice_is_handed_over_and_the_loop_moves_on
    3.00s call     drain/drain_test.py::test_read_queue_runs_on_the_in_memory_tracker_and_lists_it_once
    2.98s call     drain/drain_test.py::test_a_run_that_stops_ends_with_a_line_saying_it_stopped
    2.71s call     drain/drain_test.py::test_a_chooser_that_fails_or_says_nothing_usable_bundles_the_anchor_alone
    2.67s call     drain/drain_test.py::test_the_lowest_numbered_unit_goes_first_whether_a_ticket_or_a_spec
    2.34s call     drain/drain_test.py::test_a_chooser_past_its_wall_clock_bundles_the_anchor_alone_and_says_why
    2.15s call     drain/drain_test.py::test_a_spec_run_that_fails_hands_the_spec_and_its_claimed_slices_over_and_closes_every_pane
    1.82s call     drain/drain_test.py::test_a_pr_over_bundle_max_is_a_failed_build
    1.79s call     drain/drain_test.py::test_anchor_starts_the_bundle_from_that_ticket_and_only_the_first

Call-time sum, before / after:

    before: 153 cases listed (>=5 ms), 1031 s
    after: 153 cases listed (>=5 ms), 167 s

## Appendix: every call over 5 ms, before the fix (load 14.06 15.89 16.24)

    18.59s call     test_an_anchor_note_that_names_another_ticket_or_is_malformed_is_not_resumed
    17.05s call     test_the_lowest_numbered_unit_goes_first_whether_a_ticket_or_a_spec
    13.82s call     test_anchor_starts_the_bundle_from_that_ticket_and_only_the_first
    13.71s call     test_a_chooser_that_fails_or_says_nothing_usable_bundles_the_anchor_alone
    10.71s call     test_a_ticket_failing_twice_is_handed_over_and_the_loop_moves_on
    10.60s call     test_each_merge_runs_the_per_change_command_and_no_run_follows_the_last_bundle
    10.29s call     test_a_ready_slice_is_never_the_anchor_and_never_joins_a_bundle
    10.11s call     test_blocked_and_claimed_and_human_tickets_are_skipped
    10.04s call     test_a_ticket_whose_workspace_is_kept_is_not_picked_and_an_anchor_naming_it_is_refused
    10.03s call     test_an_anchor_this_run_ended_is_not_resumed_even_when_its_reread_is_stale
    10.02s call     test_a_merged_ticket_the_open_list_still_carries_is_not_resumed
    9.94s call     test_a_ticket_taken_since_the_pick_is_not_claimed_over
    9.94s call     test_a_repo_with_no_narrowed_line_gets_no_selector_comment_green_or_red
    9.92s call     test_an_empty_first_listing_is_read_again_before_drain_gives_up
    9.90s call     test_a_run_that_empties_the_queue_says_so_and_still_exits_zero
    9.89s call     test_a_chooser_pick_that_was_not_offered_or_is_below_the_anchor_is_dropped
    9.77s call     test_anchor_may_name_a_spec
    9.70s call     test_anchor_that_is_not_ready_or_is_blocked_is_refused_before_any_work
    8.99s call     test_two_bundles_in_a_row_handed_over_stop_the_loop
    8.73s call     test_a_run_that_stops_ends_with_a_line_saying_it_stopped
    8.28s call     test_a_spec_run_that_fails_hands_the_spec_and_its_claimed_slices_over_and_closes_every_pane
    7.83s call     test_a_chooser_past_its_wall_clock_bundles_the_anchor_alone_and_says_why
    7.69s call     test_a_seam_section_that_declares_no_command_merges_nothing_even_with_the_line
    7.69s call     test_a_candidate_count_is_never_read_as_a_ticket
    7.57s call     test_an_idle_worker_with_no_pr_is_a_failed_build_not_a_wait_forever
    7.56s call     test_a_missing_pr_prompts_with_the_reason_it_is_not_up
    7.50s call     test_a_bundle_handed_to_chris_closes_its_workers_pane
    7.43s call     test_a_failed_install_is_a_failed_build_and_the_seam_never_runs
    7.37s call     test_a_repo_without_a_lockfile_installs_nothing
    7.35s call     test_a_blocked_worker_is_a_failed_build_not_a_wait_for_the_wall_clock
    7.34s call     test_every_tracked_lockfile_gets_its_own_install
    7.32s call     test_an_npm_that_cannot_start_is_a_failed_build_not_a_crash
    7.30s call     test_a_bundle_whose_dispatch_failed_after_the_claim_is_still_announced_before_it_ends
    7.28s call     test_a_bundle_comment_left_by_an_earlier_drain_touches_nothing
    7.24s call     test_main_moving_after_a_skip_is_checked_again_before_the_merge
    7.20s call     test_a_closed_ticket_the_open_list_carries_is_not_resumed_by_a_fresh_run
    7.20s call     test_a_red_seam_leaves_its_listing_judging_nothing_and_still_blocks_the_merge
    7.19s call     test_a_punctuated_chooser_answer_is_parsed_into_every_ticket
    7.16s call     test_main_moving_during_a_rerun_is_checked_again_before_the_merge
    7.13s call     test_anything_short_of_all_three_checks_reruns[env3]
    7.12s call     test_a_worker_still_working_is_waited_for_until_it_goes_idle
    7.12s call     test_a_comment_that_cannot_be_posted_does_not_stop_a_green_merge
    7.11s call     test_a_main_moved_since_drains_last_look_reruns_though_the_seam_section_is_the_same
    7.09s call     test_a_skip_comment_that_cannot_be_posted_reruns_rather_than_merge_unrecorded
    7.08s call     test_a_pr_closing_a_ticket_the_bundle_comment_does_not_name_is_a_failed_build
    7.05s call     test_a_red_seam_is_a_failed_build
    7.04s call     test_a_rerun_gets_tests_jobs_capped_and_never_raised[x-4]
    7.04s call     test_an_open_ticket_the_list_carries_after_losing_in_progress_is_not_resumed
    7.03s call     test_a_relative_log_dir_still_gives_the_seam_its_selector_listing
    7.01s call     test_a_repo_that_declares_no_per_change_command_merges_nothing_and_says_why
    7.01s call     test_a_nested_lockfile_gets_its_dependencies_installed_in_its_own_directory
    7.01s call     test_the_agents_bundle_is_one_pr_and_the_rest_stay_ready
    7.00s call     test_a_rerun_gets_tests_jobs_capped_and_never_raised[32-4]
    6.97s call     test_anything_short_of_all_three_checks_reruns[env2]
    6.97s call     test_the_chooser_is_run_in_auto_permission_mode
    6.97s call     test_the_bundle_is_announced_while_its_worker_is_still_building
    6.96s call     test_a_run_that_reaches_once_names_the_limit_and_the_tickets_left
    6.95s call     test_a_transient_look_failure_does_not_fail_the_build
    6.95s call     test_a_lockfile_gets_its_dependencies_installed_before_the_seam_runs
    6.94s call     test_a_declared_narrowed_command_is_listed_then_run_in_place_of_the_seam
    6.94s call     test_a_run_that_reaches_max_names_the_limit_and_the_tickets_left
    6.93s call     test_anything_short_of_all_three_checks_reruns[env1]
    6.92s call     test_a_rerun_gets_tests_jobs_capped_and_never_raised[2-2]
    6.91s call     test_a_candidate_whose_body_cannot_be_read_is_listed_as_unread
    6.91s call     test_land_testcmd_is_not_what_a_merge_runs
    6.91s call     test_a_pr_that_edits_its_own_seam_section_is_gated_by_mains
    6.91s call     test_a_single_ticket_bundle_records_the_candidates_the_chooser_saw
    6.90s call     test_a_chooser_that_echoes_the_count_does_not_pick_it_as_a_ticket
    6.89s call     test_a_seam_command_with_a_trailing_semicolon_and_a_comment_runs_as_declared
    6.89s call     test_anything_short_of_all_three_checks_reruns[env0]
    6.88s call     test_once_builds_checks_merges_and_cleans_up
    6.88s call     test_a_pr_over_bundle_max_is_a_failed_build
    6.87s call     test_the_choose_log_holds_the_prompt_the_chooser_judged_from_even_when_it_fails
    6.87s call     test_a_rerun_gets_tests_jobs_capped_and_never_raised[None-4]
    6.87s call     test_a_ticket_another_worker_holds_is_not_touched_by_a_merge
    6.87s call     test_a_live_workers_ticket_is_not_adopted
    6.86s call     test_the_chooser_prompt_carries_each_candidates_body_and_comments_capped
    6.86s call     test_the_chooser_prompt_calls_a_drain_a_drain_not_a_run
    6.84s call     test_a_base_branch_modified_refusal_is_retried
    6.84s call     test_a_bundle_of_one_landed_and_one_moot_ticket_records_each_as_what_it_was
    6.82s call     test_a_drain_run_from_a_linked_worktree_names_the_primary_checkout
    6.81s call     test_a_listing_that_prints_nothing_is_not_checked_and_a_green_seam_still_merges
    6.80s call     test_the_build_is_dispatched_under_the_drain_controller_and_its_agent_is_looked_up_by_name
    6.80s call     test_a_failed_bundle_hands_every_claimed_ticket_to_chris_in_one_line
    6.80s call     test_a_non_empty_queue_never_waits_out_the_retry
    6.79s call     test_a_pr_the_wait_refuses_never_reaches_the_seam[env0]
    6.79s call     test_a_failed_check_prompts_the_worker_with_the_reason_and_waits_for_it_to_start_working
    6.79s call     test_a_merge_cleanup_failure_is_a_note_not_a_rebuild
    6.77s call     test_a_head_the_worker_ran_on_with_main_in_it_skips_the_rerun_and_says_so_on_the_pr
    6.76s call     test_a_bundle_with_no_candidates_says_zero
    6.75s call     test_a_green_seam_leaves_its_listing_on_the_pr_and_the_merge_lands
    6.75s call     test_a_merged_bundle_gets_an_end_line_with_its_pr_and_sha
    6.75s call     test_the_choosers_bundle_is_cut_to_bundle_max
    6.74s call     test_a_bundle_handed_to_chris_gets_an_end_line_with_the_reason
    6.73s call     test_a_queue_of_one_spec_and_its_slices_is_dispatched_as_a_spec_run_and_merged
    6.72s call     test_a_ticket_the_agent_claimed_but_the_pr_did_not_close_goes_back_to_ready
    6.71s call     test_the_seam_runs_on_the_pr_merged_into_current_main
    6.71s call     test_a_chooser_that_fails_leaves_a_comment_saying_so
    6.71s call     test_a_spec_pr_may_close_more_tickets_than_bundle_max_when_all_are_its_slices
    6.71s call     test_a_spec_pr_that_closes_a_ticket_that_is_not_its_slice_is_a_failed_build
    6.70s call     test_a_spec_drain_cannot_start_is_named_when_the_run_ends_on_a_limit
    6.70s call     test_a_pr_that_does_not_close_the_anchor_is_a_failed_build
    6.70s call     test_an_unknown_pr_is_waited_on_until_clean
    6.70s call     test_a_dispatch_that_fails_after_the_claim_is_this_bundles_failed_build
    6.69s call     test_a_spec_pr_that_does_not_close_the_spec_is_a_failed_build
    6.67s call     test_a_failed_check_is_a_failed_build_without_a_wait
    6.66s call     test_a_limit_exit_lists_what_is_ready_now_not_what_was_ready_at_the_last_read
    6.65s call     test_a_pr_the_wait_refuses_never_reaches_the_seam[env1]
    6.64s call     test_a_stranded_slice_is_named_even_when_another_ticket_is_started
    6.64s call     test_a_worker_that_is_gone_with_no_pr_is_a_failed_build
    6.63s call     test_a_light_tier_worker_that_landed_on_main_with_no_pr_is_a_merge
    6.63s call     test_a_pr_that_is_not_clean_is_a_failed_build
    6.61s call     test_a_landed_ticket_is_recorded_with_the_commit_that_closed_it_not_mains_tip
    6.54s call     test_a_close_whose_cause_cannot_be_read_is_not_called_landed_or_moot
    6.49s call     test_a_closing_commit_git_cannot_find_says_it_could_not_be_checked_not_that_it_is_off_main
    6.49s call     test_a_ticket_closed_by_hand_whose_commit_on_main_says_closes_is_landed_not_moot
    6.49s call     test_a_ticket_closed_by_hand_is_moot_with_no_sha_and_never_landed
    6.46s call     test_a_closing_commit_that_is_not_on_main_is_not_called_landed
    6.39s call     test_every_ready_ticket_drain_passed_over_is_named_with_its_reason
    6.35s call     test_a_one_slice_spec_whose_run_lands_it_without_an_integration_pr_is_reported_landed
    6.28s call     test_a_blocked_spec_is_not_dispatched
    6.28s call     test_a_ticket_drain_handed_to_chris_is_not_adopted_when_it_is_readied_again
    6.28s call     test_a_ticket_claimed_by_an_assignee_alone_is_not_said_to_carry_in_progress
    6.28s call     test_no_merge_means_no_run
    6.25s call     test_a_spec_the_run_did_not_start_is_never_taken
    6.24s call     test_a_spec_without_the_ready_label_is_not_dispatched
    6.23s call     test_once_drains_a_ticket_through_the_in_memory_tracker_with_no_gh
    6.22s call     test_a_listing_that_stays_empty_is_read_once_more_and_not_again
    6.22s call     test_an_empty_queue_says_so
    6.21s call     test_a_slice_of_a_closed_spec_is_named_not_left_behind
    6.16s call     test_a_herdr_that_hangs_stops_the_drain_naming_herdr
    3.81s call     test_a_herdr_that_cannot_be_asked_stops_the_drain
    3.69s call     test_a_bundle_cut_short_by_a_stop_gets_a_stopped_end_line
    3.69s call     test_a_rerun_checks_an_open_pr_without_rebuilding
    3.58s call     test_a_rerun_with_a_gone_worker_and_no_pr_hands_the_ticket_over
    3.41s call     test_a_rerun_resumes_a_spec_it_started_and_never_dispatches_it_twice
    3.35s call     test_a_dispatch_refusal_stops_the_drain_and_leaves_the_ticket_ready
    3.35s call     test_a_resumed_anchor_under_once_still_reads_the_queue_to_say_what_it_passed_over
    3.28s call     test_a_refused_dispatch_announces_no_bundle
    3.22s call     test_a_failed_claim_comment_leaves_the_ticket_ready
    3.20s call     test_a_spec_whose_workspace_is_kept_is_not_picked_again
    3.15s call     test_an_anchor_refusal_does_not_claim_the_queue_was_never_read
    3.15s call     test_a_ready_ticket_with_a_kept_workspace_is_named_as_passed_over
    3.00s call     test_read_queue_runs_on_the_in_memory_tracker_and_lists_it_once
    1.00s call     test_run_group_kills_what_a_command_started
    0.40s call     test_a_spec_run_gets_the_spec_wall_clock_not_the_tickets
    0.30s call     test_a_live_job_does_not_outlast_the_wall_clock
    0.30s call     test_a_worker_that_never_goes_idle_fails_at_the_wall_clock
    0.20s call     test_the_same_idle_wait_with_no_slice_working_fails_at_the_grace
    0.20s call     test_the_wait_asks_for_the_jobs_of_the_workers_own_workspace
    0.20s call     test_a_blocked_worker_is_not_held_by_a_live_job
    0.11s call     test_refuses_a_repo_the_user_does_not_own
    0.03s call     test_the_nudge_calls_a_drain_a_drain_not_a_run

## Appendix: every call over 5 ms, after the fix (load 20.29 17.39 16.52)

    6.24s call     test_once_drains_a_ticket_through_the_in_memory_tracker_with_no_gh
    3.14s call     test_a_herdr_that_hangs_stops_the_drain_naming_herdr
    3.08s call     test_two_bundles_in_a_row_handed_over_stop_the_loop
    3.05s call     test_a_ticket_failing_twice_is_handed_over_and_the_loop_moves_on
    3.00s call     test_read_queue_runs_on_the_in_memory_tracker_and_lists_it_once
    2.98s call     test_a_run_that_stops_ends_with_a_line_saying_it_stopped
    2.71s call     test_a_chooser_that_fails_or_says_nothing_usable_bundles_the_anchor_alone
    2.67s call     test_the_lowest_numbered_unit_goes_first_whether_a_ticket_or_a_spec
    2.34s call     test_a_chooser_past_its_wall_clock_bundles_the_anchor_alone_and_says_why
    2.15s call     test_a_spec_run_that_fails_hands_the_spec_and_its_claimed_slices_over_and_closes_every_pane
    1.82s call     test_a_pr_over_bundle_max_is_a_failed_build
    1.79s call     test_anchor_starts_the_bundle_from_that_ticket_and_only_the_first
    1.77s call     test_a_candidate_count_is_never_read_as_a_ticket
    1.71s call     test_a_missing_pr_prompts_with_the_reason_it_is_not_up
    1.69s call     test_blocked_and_claimed_and_human_tickets_are_skipped
    1.67s call     test_a_bundle_handed_to_chris_closes_its_workers_pane
    1.62s call     test_each_merge_runs_the_per_change_command_and_no_run_follows_the_last_bundle
    1.59s call     test_the_agents_bundle_is_one_pr_and_the_rest_stay_ready
    1.58s call     test_the_choosers_bundle_is_cut_to_bundle_max
    1.57s call     test_a_red_seam_leaves_its_listing_judging_nothing_and_still_blocks_the_merge
    1.56s call     test_a_bundle_comment_left_by_an_earlier_drain_touches_nothing
    1.55s call     test_a_chooser_pick_that_was_not_offered_or_is_below_the_anchor_is_dropped
    1.51s call     test_a_blocked_worker_is_a_failed_build_not_a_wait_for_the_wall_clock
    1.50s call     test_the_chooser_is_run_in_auto_permission_mode
    1.50s call     test_an_idle_worker_with_no_pr_is_a_failed_build_not_a_wait_forever
    1.49s call     test_a_ticket_the_agent_claimed_but_the_pr_did_not_close_goes_back_to_ready
    1.49s call     test_once_builds_checks_merges_and_cleans_up
    1.46s call     test_a_ready_slice_is_never_the_anchor_and_never_joins_a_bundle
    1.46s call     test_the_chooser_prompt_carries_each_candidates_body_and_comments_capped
    1.46s call     test_a_ticket_whose_workspace_is_kept_is_not_picked_and_an_anchor_naming_it_is_refused
    1.44s call     test_a_red_seam_is_a_failed_build
    1.41s call     test_a_pr_that_does_not_close_the_anchor_is_a_failed_build
    1.38s call     test_a_candidate_whose_body_cannot_be_read_is_listed_as_unread
    1.37s call     test_a_failed_bundle_hands_every_claimed_ticket_to_chris_in_one_line
    1.36s call     test_the_build_is_dispatched_under_the_drain_controller_and_its_agent_is_looked_up_by_name
    1.35s call     test_a_ticket_taken_since_the_pick_is_not_claimed_over
    1.32s call     test_the_choose_log_holds_the_prompt_the_chooser_judged_from_even_when_it_fails
    1.30s call     test_a_punctuated_chooser_answer_is_parsed_into_every_ticket
    1.29s call     test_the_seam_runs_on_the_pr_merged_into_current_main
    1.28s call     test_a_bundle_whose_dispatch_failed_after_the_claim_is_still_announced_before_it_ends
    1.27s call     test_a_chooser_that_fails_leaves_a_comment_saying_so
    1.25s call     test_a_single_ticket_bundle_records_the_candidates_the_chooser_saw
    1.24s call     test_a_transient_look_failure_does_not_fail_the_build
    1.24s call     test_a_seam_section_that_declares_no_command_merges_nothing_even_with_the_line
    1.23s call     test_a_base_branch_modified_refusal_is_retried
    1.22s call     test_a_repo_with_no_narrowed_line_gets_no_selector_comment_green_or_red
    1.22s call     test_the_chooser_prompt_calls_a_drain_a_drain_not_a_run
    1.18s call     test_an_anchor_this_run_ended_is_not_resumed_even_when_its_reread_is_stale
    1.16s call     test_a_spec_pr_that_closes_a_ticket_that_is_not_its_slice_is_a_failed_build
    1.16s call     test_a_pr_that_is_not_clean_is_a_failed_build
    1.16s call     test_a_worker_still_working_is_waited_for_until_it_goes_idle
    1.15s call     test_an_empty_first_listing_is_read_again_before_drain_gives_up
    1.14s call     test_a_pr_the_wait_refuses_never_reaches_the_seam[env0]
    1.13s call     test_a_repo_that_declares_no_per_change_command_merges_nothing_and_says_why
    1.13s call     test_a_chooser_that_echoes_the_count_does_not_pick_it_as_a_ticket
    1.13s call     test_a_relative_log_dir_still_gives_the_seam_its_selector_listing
    1.11s call     test_a_failed_check_is_a_failed_build_without_a_wait
    1.11s call     test_an_unknown_pr_is_waited_on_until_clean
    1.10s call     test_a_pr_closing_a_ticket_the_bundle_comment_does_not_name_is_a_failed_build
    1.10s call     test_a_drain_run_from_a_linked_worktree_names_the_primary_checkout
    1.09s call     test_an_anchor_note_that_names_another_ticket_or_is_malformed_is_not_resumed
    1.09s call     test_a_run_that_reaches_once_names_the_limit_and_the_tickets_left
    1.09s call     test_a_green_seam_leaves_its_listing_on_the_pr_and_the_merge_lands
    1.09s call     test_a_ticket_another_worker_holds_is_not_touched_by_a_merge
    1.08s call     test_a_comment_that_cannot_be_posted_does_not_stop_a_green_merge
    1.07s call     test_the_bundle_is_announced_while_its_worker_is_still_building
    1.06s call     test_main_moving_during_a_rerun_is_checked_again_before_the_merge
    1.05s call     test_a_pr_the_wait_refuses_never_reaches_the_seam[env1]
    1.05s call     test_a_listing_that_prints_nothing_is_not_checked_and_a_green_seam_still_merges
    1.04s call     test_an_npm_that_cannot_start_is_a_failed_build_not_a_crash
    1.04s call     test_every_tracked_lockfile_gets_its_own_install
    1.04s call     test_a_failed_install_is_a_failed_build_and_the_seam_never_runs
    1.03s call     test_a_merged_ticket_the_open_list_still_carries_is_not_resumed
    1.03s call     test_a_failed_check_prompts_the_worker_with_the_reason_and_waits_for_it_to_start_working
    1.02s call     test_a_limit_exit_lists_what_is_ready_now_not_what_was_ready_at_the_last_read
    1.01s call     test_a_run_that_empties_the_queue_says_so_and_still_exits_zero
    1.00s call     test_a_spec_pr_that_does_not_close_the_spec_is_a_failed_build
    1.00s call     test_run_group_kills_what_a_command_started
    0.99s call     test_a_spec_pr_may_close_more_tickets_than_bundle_max_when_all_are_its_slices
    0.99s call     test_main_moving_after_a_skip_is_checked_again_before_the_merge
    0.97s call     test_a_merged_bundle_gets_an_end_line_with_its_pr_and_sha
    0.95s call     test_a_lockfile_gets_its_dependencies_installed_before_the_seam_runs
    0.95s call     test_a_closed_ticket_the_open_list_carries_is_not_resumed_by_a_fresh_run
    0.95s call     test_a_merge_cleanup_failure_is_a_note_not_a_rebuild
    0.95s call     test_an_open_ticket_the_list_carries_after_losing_in_progress_is_not_resumed
    0.95s call     test_a_repo_without_a_lockfile_installs_nothing
    0.94s call     test_a_stranded_slice_is_named_even_when_another_ticket_is_started
    0.94s call     test_a_seam_command_with_a_trailing_semicolon_and_a_comment_runs_as_declared
    0.94s call     test_a_declared_narrowed_command_is_listed_then_run_in_place_of_the_seam
    0.93s call     test_a_skip_comment_that_cannot_be_posted_reruns_rather_than_merge_unrecorded
    0.93s call     test_anchor_may_name_a_spec
    0.92s call     test_a_bundle_handed_to_chris_gets_an_end_line_with_the_reason
    0.92s call     test_a_live_workers_ticket_is_not_adopted
    0.91s call     test_a_queue_of_one_spec_and_its_slices_is_dispatched_as_a_spec_run_and_merged
    0.90s call     test_a_bundle_with_no_candidates_says_zero
    0.89s call     test_a_rerun_gets_tests_jobs_capped_and_never_raised[None-4]
    0.89s call     test_a_run_that_reaches_max_names_the_limit_and_the_tickets_left
    0.88s call     test_a_nested_lockfile_gets_its_dependencies_installed_in_its_own_directory
    0.88s call     test_a_non_empty_queue_never_waits_out_the_retry
    0.87s call     test_a_pr_that_edits_its_own_seam_section_is_gated_by_mains
    0.85s call     test_a_main_moved_since_drains_last_look_reruns_though_the_seam_section_is_the_same
    0.84s call     test_anything_short_of_all_three_checks_reruns[env3]
    0.84s call     test_a_bundle_of_one_landed_and_one_moot_ticket_records_each_as_what_it_was
    0.83s call     test_a_spec_drain_cannot_start_is_named_when_the_run_ends_on_a_limit
    0.82s call     test_anything_short_of_all_three_checks_reruns[env2]
    0.81s call     test_anything_short_of_all_three_checks_reruns[env0]
    0.80s call     test_a_dispatch_that_fails_after_the_claim_is_this_bundles_failed_build
    0.79s call     test_land_testcmd_is_not_what_a_merge_runs
    0.79s call     test_a_bundle_cut_short_by_a_stop_gets_a_stopped_end_line
    0.79s call     test_a_rerun_gets_tests_jobs_capped_and_never_raised[x-4]
    0.78s call     test_anything_short_of_all_three_checks_reruns[env1]
    0.78s call     test_a_rerun_gets_tests_jobs_capped_and_never_raised[32-4]
    0.75s call     test_a_rerun_gets_tests_jobs_capped_and_never_raised[2-2]
    0.75s call     test_a_head_the_worker_ran_on_with_main_in_it_skips_the_rerun_and_says_so_on_the_pr
    0.75s call     test_a_herdr_that_cannot_be_asked_stops_the_drain
    0.70s call     test_a_rerun_checks_an_open_pr_without_rebuilding
    0.68s call     test_anchor_that_is_not_ready_or_is_blocked_is_refused_before_any_work
    0.67s call     test_a_landed_ticket_is_recorded_with_the_commit_that_closed_it_not_mains_tip
    0.66s call     test_a_one_slice_spec_whose_run_lands_it_without_an_integration_pr_is_reported_landed
    0.66s call     test_a_worker_that_is_gone_with_no_pr_is_a_failed_build
    0.62s call     test_a_closing_commit_git_cannot_find_says_it_could_not_be_checked_not_that_it_is_off_main
    0.62s call     test_a_ticket_closed_by_hand_is_moot_with_no_sha_and_never_landed
    0.60s call     test_a_light_tier_worker_that_landed_on_main_with_no_pr_is_a_merge
    0.59s call     test_a_closing_commit_that_is_not_on_main_is_not_called_landed
    0.56s call     test_a_close_whose_cause_cannot_be_read_is_not_called_landed_or_moot
    0.54s call     test_a_resumed_anchor_under_once_still_reads_the_queue_to_say_what_it_passed_over
    0.53s call     test_a_ticket_closed_by_hand_whose_commit_on_main_says_closes_is_landed_not_moot
    0.52s call     test_a_rerun_with_a_gone_worker_and_no_pr_hands_the_ticket_over
    0.49s call     test_every_ready_ticket_drain_passed_over_is_named_with_its_reason
    0.49s call     test_a_blocked_spec_is_not_dispatched
    0.47s call     test_a_rerun_resumes_a_spec_it_started_and_never_dispatches_it_twice
    0.44s call     test_a_dispatch_refusal_stops_the_drain_and_leaves_the_ticket_ready
    0.44s call     test_a_spec_the_run_did_not_start_is_never_taken
    0.42s call     test_a_refused_dispatch_announces_no_bundle
    0.40s call     test_a_spec_run_gets_the_spec_wall_clock_not_the_tickets
    0.39s call     test_a_slice_of_a_closed_spec_is_named_not_left_behind
    0.38s call     test_a_spec_without_the_ready_label_is_not_dispatched
    0.37s call     test_a_ticket_drain_handed_to_chris_is_not_adopted_when_it_is_readied_again
    0.34s call     test_an_empty_queue_says_so
    0.32s call     test_a_ticket_claimed_by_an_assignee_alone_is_not_said_to_carry_in_progress
    0.31s call     test_a_listing_that_stays_empty_is_read_once_more_and_not_again
    0.31s call     test_no_merge_means_no_run
    0.30s call     test_a_live_job_does_not_outlast_the_wall_clock
    0.30s call     test_a_worker_that_never_goes_idle_fails_at_the_wall_clock
    0.28s call     test_a_failed_claim_comment_leaves_the_ticket_ready
    0.25s call     test_a_ready_ticket_with_a_kept_workspace_is_named_as_passed_over
    0.21s call     test_a_spec_whose_workspace_is_kept_is_not_picked_again
    0.20s call     test_the_same_idle_wait_with_no_slice_working_fails_at_the_grace
    0.20s call     test_a_blocked_worker_is_not_held_by_a_live_job
    0.20s call     test_the_wait_asks_for_the_jobs_of_the_workers_own_workspace
    0.17s call     test_an_anchor_refusal_does_not_claim_the_queue_was_never_read
    0.11s call     test_refuses_a_repo_the_user_does_not_own
    0.01s call     test_the_nudge_calls_a_drain_a_drain_not_a_run
