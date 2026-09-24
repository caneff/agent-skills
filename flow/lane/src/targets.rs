//! Which paths a ticket body names, and whether one of them is code.
//!
//! `implement-dispatch` reads a ticket's tier off its `documentation` label,
//! and a label a filer put on by hand is not evidence about the diff (#969:
//! a `SKILL.md` change went out light and landed on main with no reviewer).
//! So the body's own targets are read too. `flow/claude/WORKFLOW.md` § Gate 2
//! names what is code; this is the dispatcher's reading of it, and it errs
//! toward code — a wrong heavy tier costs one review, a wrong light tier
//! lands code unreviewed. It reads a body's tokens, so it can only see a path
//! with an extension: an extensionless script is invisible here, where
//! `burndown/tier.py` (which reads a candidate's file list) calls it code and
//! strips the label before dispatch.

/// Extensions § Gate 2 names as code, plus the ones that wire the harness or
/// CI (its "hooks, CI config").
const CODE_EXTENSIONS: &[&str] = &[
    "py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "sh", "bash", "rs", "yml", "yaml", "toml", "json",
];
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
    if CODE_BASENAMES.contains(&name.as_str()) {
        return true;
    }
    match name.rsplit_once('.') {
        Some((stem, ext)) => !stem.is_empty() && CODE_EXTENSIONS.contains(&ext),
        None => false,
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
    fn prose_and_bare_words_are_not_code() {
        assert_eq!(first_code_target("Add docs/research/note.md and update AGENTS.md. Use rust, not a .rs-less thing"), None);
        assert_eq!(first_code_target(""), None);
    }
}
