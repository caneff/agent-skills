//! Shared library for the `/implement` lane's Rust commands. Scope is
//! exactly what both binaries use today: the base-branch resolver, the
//! sessions-registry reader, and a command runner. Nothing built ahead for
//! the multi-worker supervisor.

pub mod git_origin;
pub mod proc_info;
pub mod runner;
pub mod sessions;
