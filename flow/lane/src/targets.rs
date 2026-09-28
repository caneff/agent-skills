//! Which paths a ticket body names, and whether one of them is code.
//!
//! `implement-dispatch` reads a ticket's tier off its `documentation` label,
//! and a label a filer put on by hand is not evidence about the diff (#969:
//! a `SKILL.md` change went out light and landed on main with no reviewer).
//! So the body's own targets are read too. `flow/claude/WORKFLOW.md` § Gate 2
//! names what is code; this is the dispatcher's reading of it. A wrong heavy
//! tier costs one review and a wrong light tier lands code unreviewed, so it
//! errs toward code wherever a body's tokens let it. A token with a `/` is a
//! path, and is code unless its extension is prose (`.md .markdown .txt
//! .rst`): a whitelist, as in `burndown/tier.py`. A bare token is the
//! exception. It is code only by a fixed list of extensions, a blacklist,
//! because prose is full of dotted words that are not files (`i.e`, `v1.2`,
//! `user.email`), so a bare token with an unlisted extension (`build.gradle`)
//! reads as prose here. Extensionless, a token is code by basename
//! (`Makefile`, `Gemfile`) or under a script directory (`bin/`, `hooks/`); any
//! other extensionless name reads as prose too. `tier.py` strips the label
//! for both gaps before dispatch, from the clumper's file list. `tier.py` also
//! copies the lists below to read a body as this does (#1211), and
//! `burndown/tier_test.py` fails when a list here changes and its copy doesn't.

/// Extensions read as code: § Gate 2's, the ones that wire the harness or CI
/// (its "hooks, CI config"), and other scripting and config languages.
const CODE_EXTENSIONS: &[&str] = &[
    "py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "sh", "bash", "rs", "yml", "yaml", "toml", "json", "go", "zsh",
    "fish", "ps1", "psm1", "bat", "cmd", "lua", "ini", "cfg", "conf", "rb", "pl", "php", "java", "kt", "swift",
    "c", "h", "cpp", "hpp", "mk",
];
/// A directory whose extensionless entries are scripts: `bin/implement-dispatch`, a git hook.
const CODE_DIRS: &[&str] = &["bin", "sbin", "hooks", ".githooks", ".husky"];
/// Extensions `burndown/tier.py` reads as prose; on a path (a token with a `/`),
/// any other extension is code.
const PROSE_EXTENSIONS: &[&str] = &["md", "markdown", "txt", "rst"];
/// Product names that end in a code extension but are prose. Only the one
/// the tests exercise; an unlisted one reads as code, the cheap error.
const PROSE_TOKENS: &[&str] = &["node.js"];
/// Basenames that are code wherever they sit, whatever their extension: a
/// skill's body changes what every later session does, and the rest are
/// extensionless build and run files.
const CODE_BASENAMES: &[&str] = &["skill.md", "makefile", "dockerfile", "justfile", "rakefile", "gemfile", "procfile"];

/// The first path-shaped token in `body` that is code, if any. A token is
/// path-shaped when it holds only `/ - _ .` besides letters and digits;
/// trailing sentence punctuation is dropped. It is code by extension, by
/// filename, or as an extensionless entry under a script directory.
pub fn first_code_target(body: &str) -> Option<String> {
    // A Windows path separator is a path separator, as `tier.py` reads it.
    body.replace('\\', "/")
        .split(|c: char| !(c.is_alphanumeric() || "/-_.".contains(c)))
        .map(|t| t.trim_end_matches('.'))
        .find(|t| is_code_path(t))
        .map(str::to_string)
}

fn is_code_path(token: &str) -> bool {
    let name = token.rsplit('/').next().unwrap_or(token).to_ascii_lowercase();
    if CODE_BASENAMES.contains(&name.as_str()) {
        return true;
    }
    if !token.contains('/') && PROSE_TOKENS.contains(&name.as_str()) {
        return false;
    }
    match name.rsplit_once('.') {
        Some((stem, ext)) => {
            // On a path, a dotfile's name is its extension (`config/.env`), as in `tier.py`.
            (!stem.is_empty() && CODE_EXTENSIONS.contains(&ext))
                || (token.contains('/') && ext.chars().any(|c| c.is_alphabetic()) && !PROSE_EXTENSIONS.contains(&ext))
        }
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
    fn a_slash_path_is_code_unless_its_extension_is_prose() {
        for p in ["src/main.dart", "tools/Gemfile", "a/b.sql", "x/y.lua", "infra/main.tf", "Gemfile", "lib/Rakefile", "config/.env", "x/.eslintrc"] {
            assert_eq!(first_code_target(&format!("see {p}, then")), Some(p.into()), "{p}");
        }
        for body in ["read/write and and/or", "docs/notes.md", "a/b.txt", "a/b.rst", "a/b.markdown", "ratio 3/4.5 here", "docs/.notes.md"] {
            assert_eq!(first_code_target(body), None, "{body}");
        }
    }

    /// The prose whitelist is written twice, here and in `burndown/tier.py`,
    /// and a file one reader calls prose and the other calls code dispatches
    /// at a tier the other never agreed to. Read tier.py's literal and compare.
    #[test]
    fn the_prose_whitelist_matches_tier_py() {
        let src = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../burndown/tier.py")).unwrap();
        let line = src.lines().find(|l| l.starts_with("PROSE_EXTENSIONS = {")).expect("tier.py defines PROSE_EXTENSIONS on one line");
        let mut theirs: Vec<&str> = line.split('"').skip(1).step_by(2).collect();
        let mut ours = PROSE_EXTENSIONS.to_vec();
        theirs.sort_unstable();
        ours.sort_unstable();
        assert!(!theirs.is_empty(), "no extensions parsed from: {line}");
        assert_eq!(ours, theirs, "targets.rs PROSE_EXTENSIONS and burndown/tier.py's disagree");
    }

    #[test]
    fn a_backslash_path_reads_like_a_slash_path() {
        // `tier.py` normalises `\` to `/` before it classifies; so does this.
        assert_eq!(first_code_target(r"see bin\implement-dispatch, then").as_deref(), Some("bin/implement-dispatch"));
        assert_eq!(first_code_target(r"edit .githooks\pre-push").as_deref(), Some(".githooks/pre-push"));
        assert_eq!(first_code_target(r"src\main.dart"), Some("src/main.dart".into()));
        assert_eq!(first_code_target(r"docs\notes.md"), None);
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
