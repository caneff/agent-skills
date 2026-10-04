# Sourced by install.sh (what to link) and install-check.sh (what must be
# linked and registered), so the two cannot disagree about the hook set.

# Hooks linked into ~/.claude/hooks. A lib sits here too: the hook that sources
# it resolves it beside the link, and a lib not linked made every stop log
# lib-missing for two days (#1148, #1224).
LINKED_HOOKS=(block-dangerous-git.sh refresh-landed.sh
              wrap-background-jobs.sh worker-stop-alert.sh
              worker-alert-lib.sh package.json)

# Repo hooks with no settings.json entry on purpose. worker-stop-alert.sh is
# linked but its Stop entry was removed 2026-10-04 (flow/claude/OPERATIONS.md
# § worker-stop-alert); re-adding the entry restores it.
UNREGISTERED_BY_DESIGN=(worker-stop-alert.sh)
