# One obvious entrypoint for the gate — agents and CI run `just check`.

# Full gate (what CI runs). Run before calling any task done.
check: lint typecheck test

lint:
    uv run ruff check .
    uv run ruff format --check .

# Auto-fix + format in place.
fmt:
    uv run ruff check --fix .
    uv run ruff format .

typecheck:
    uv run ty check

test:
    uv run pytest
