# Sourced by install.sh (what to link) and install-check.sh (what must be
# linked and registered), so the two cannot disagree about the hook set.

# Hooks linked into ~/.claude/hooks. A lib sits here too: the hook that sources
# it resolves it beside the link, and a lib not linked made every stop log
# lib-missing for two days (#1148, #1224).
LINKED_HOOKS=(block-dangerous-git.sh refresh-landed.sh
              wrap-background-jobs.sh worker-stop-alert.sh
              worker-alert-lib.sh package.json)

# Repo hooks with no settings.json entry on purpose. worker-stop-alert.sh is
# linked but its Stop entry was removed 2026-10-04 (flow/claude/OPERATIONS.md,
# the `Stop` hook paragraph under § Wait); re-adding the entry restores it.
UNREGISTERED_BY_DESIGN=(worker-stop-alert.sh)

# Scripts in claude/hooks/ that are sourced, never run as a hook, so no
# settings.json entry exists for them. Named, not matched by a `*-lib.sh`
# glob: a new hook with a library-sounding name must not skip the check.
# install-check.sh fails when a name here no longer exists.
SOURCED_LIBS=(command-scan-lib.sh worker-alert-lib.sh teach-lib.sh teach-testlib.sh)
