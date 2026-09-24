//! Which paths a ticket body names, and whether one of them is code.
//!
//! `implement-dispatch` reads a ticket's tier off its `documentation` label,
//! and a label a filer put on by hand is not evidence about the diff (#969:
//! a `SKILL.md` change went out light and landed on main with no reviewer).
//! So the body's own targets are read too. `flow/claude/WORKFLOW.md` § Gate 2
//! names what is code; this is the dispatcher's reading of it, and it errs
//! toward code — a wrong heavy tier costs one review, a wrong light tier
//! lands code unreviewed. It reads a body's tokens, not a file list, so it
//! cannot treat everything outside prose as code the way `burndown/tier.py`
//! does (`i.e`, `v1.2` would all go heavy): it names a fixed list of code
//! extensions, a few extensionless filenames, and extensionless entries under
//! a script directory (`bin/`, `hooks/`). A path outside all three is still
//! invisible here; `tier.py` strips the label for it before dispatch.

/// Extensions § Gate 2 names as code, plus the ones that wire the harness or
/// CI (its "hooks, CI config").
const CODE_EXTENSIONS: &[&str] = &[
    "py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "sh", "bash", "rs", "yml", "yaml", "toml", "json", "go", "zsh",
    "fish", "ps1", "psm1", "bat", "cmd", "lua", "ini", "cfg", "conf", "rb", "pl", "php", "java", "kt", "swift",
    "c", "h", "cpp", "hpp", "mk",
];
/// Extensionless files that are code wherever they sit.
const CODE_FILENAMES: &[&str] = &["makefile", "dockerfile", "justfile", "rakefile", "procfile"];
/// A directory whose extensionless entries are scripts: `bin/implement-dispatch`, a git hook.
const CODE_DIRS: &[&str] = &["bin", "sbin", "hooks", ".githooks", ".husky"];
/// Product names that end in a code extension but are prose.
const PROSE_TOKENS: &[&str] = &["node.js", "next.js", "vue.js", "three.js", "d3.js", "express.js"];
/// Basenames that are code whatever their extension: a skill's body changes
/// what every later session does, and `settings.json` wires the harness.
const CODE_BASENAMES: &[&str] = &["skill.md"];

/// The first path-shaped token in `body` that is code, if any. A token is
/// path-shaped when it has an extension after its last `.` and no other
/// punctuation than `/ - _ .`; trailing sentence punctuation is dropped.
pub fn first_code_target(body: &str) -> Option<String> {
    body.split(|c: char| !(c.is_alphanumeric() || "/-_.".contains(c)))
        .map(|t| t.trim_end_matches('.'))
        .find(|t| is_code_path(t))
        .map(str::to_string)
}

fn is_code_path(token: &str) -> bool {
    let name = token.rsplit('/').next().unwrap_or(token).to_ascii_lowercase();
    if CODE_BASENAMES.contains(&name.as_str()) || CODE_FILENAMES.contains(&name.as_str()) {
        return true;
    }
    if !token.contains('/') && PROSE_TOKENS.contains(&name.as_str()) {
        return false;
    }
    match name.rsplit_once('.') {
        Some((stem, ext)) => !stem.is_empty() && CODE_EXTENSIONS.contains(&ext),
        None => token.contains('/') && token.split('/').rev().skip(1).any(|d| CODE_DIRS.contains(&d.to_ascii_lowercase().as_str())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_a_skill_body_at_any_depth() {
        assert_eq!(first_code_target("edit `multi-axis-code-review/SKILL.md` § 6").as_deref(), Some("multi-axis-code-review/SKILL.md"));
        assert_eq!(first_code_target("SKILL.md."), Some("SKILL.md".into()));
    }

    #[test]
    fn names_the_gate_two_code_extensions() {
        for p in [
            "a/b.py", "x.ts", "x.js", "hooks/g.sh", "src/lib.rs", "settings.json", ".github/workflows/ci.yml", "Cargo.toml",
            "hooks/x.bash", "a.tsx", "a.mjs", "settings.local.json",
        ] {
            assert_eq!(first_code_target(&format!("see {p}, then")), Some(p.into()), "{p}");
        }
    }

    #[test]
    fn names_extensionless_scripts_and_unlisted_extensions() {
        for p in [
            "bin/implement-dispatch", "Makefile", "build/Dockerfile", ".githooks/pre-push", "hooks/commit-msg",
            "a.go", "a.zsh", "a.ps1", "a.lua", "a.ini", "a.cfg", "x/y.rb",
        ] {
            assert_eq!(first_code_target(&format!("see {p}, then")), Some(p.into()), "{p}");
        }
    }

    #[test]
    fn ordinary_prose_tokens_are_not_code() {
        for body in ["i.e. this", "e.g. that", "bump to v1.2 now", "runs on Node.js", "read/write and/or edit", "version 3.10.2"] {
            assert_eq!(first_code_target(body), None, "{body}");
        }
        // A product name is prose; a path ending in one is a file.
        assert_eq!(first_code_target("edit scripts/node.js"), Some("scripts/node.js".into()));
    }

    #[test]
    fn prose_and_bare_words_are_not_code() {
        assert_eq!(first_code_target("Add docs/research/note.md and update AGENTS.md. Use rust, not a .rs-less thing"), None);
        assert_eq!(first_code_target(""), None);
    }
}
