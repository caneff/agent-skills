#!/usr/bin/env bash
# Runs skills-sync.sh's own --self-test.
set -euo pipefail
exec bash "$(cd "$(dirname "$0")" && pwd)/skills-sync.sh" --self-test
