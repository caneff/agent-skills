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
