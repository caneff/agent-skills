# Sourced, not run. Exports one persistent CARGO_TARGET_DIR for every suite that
# compiles the lane crate (flow/lane's `cargo test`, flow/install.test.sh's
# `cargo install`), so the dependencies compile once and only the lane crate
# rebuilds (#1950). A caller's own value wins: a mutation worktree sets its own
# so a mutated build is never reused (implement/SKILL.md § Build).
#
# Concurrent cargo runs on this dir wait on cargo's own build-directory lock. A
# waiting cargo is blocked, not computing, so the wait costs no CPU and cannot
# push a suite over its `cpu_budget`; it costs wall time, at most one cold
# compile of the dependencies (~110 s), once, far inside the 590 s worker cap.
: "${CARGO_TARGET_DIR:=${XDG_CACHE_HOME:-$HOME/.cache}/agent-skills/cargo-target}"
export CARGO_TARGET_DIR
