//! Shared library for the `/implement` lane's Rust commands: the
//! base-branch resolver, the sessions-registry and worker-sidecar readers,
//! typed herdr and `gh` output, worktree reads, code-target classification,
//! atomic file replacement and a command runner. A module lands here when a
//! command uses it, never ahead of one.

pub mod atomic;
pub mod git_origin;
pub mod herdr;
pub mod io_safe;
pub mod issue_state;
pub mod proc_info;
pub mod runner;
pub mod sessions;
pub mod targets;
pub mod workers;
pub mod worktree;
pub mod worktree_files;
