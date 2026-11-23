#!/usr/bin/env bash
# Run a sudoku-kit command (solve-guide, solve-deductions, python ...) against
# the checkout $SUDOKU_KIT names, default ~/src/sudoku-kit, from the caller's
# own directory, so relative paths keep meaning what they say:
#
#   kit.sh <command> [args...]
#
# Stopgap until sudoku-kit#127 reaches main: a checkout without the guide
# library (src/sudoku_kit/guide_file.py) is refused, exit 2, before anything
# runs, and so is a path with no checkout at all. Otherwise the command's own
# exit status is kit.sh's.
set -u
kit=${SUDOKU_KIT:-$HOME/src/sudoku-kit}
if [ ! -d "$kit" ]; then
  echo "kit.sh: no checkout at $kit: set SUDOKU_KIT to a sudoku-kit checkout" >&2
  exit 2
fi
if [ ! -f "$kit/src/sudoku_kit/guide_file.py" ]; then
  echo "kit.sh: $kit has no guide library (src/sudoku_kit/guide_file.py); until sudoku-kit#127 reaches main, set SUDOKU_KIT to a checkout of origin/spec-127" >&2
  exit 2
fi
exec uv run --quiet --project "$kit" "$@"
