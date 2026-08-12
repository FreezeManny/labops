# ----------- DEVCONTAINER ------
container-start:
	devcontainer up --workspace-folder .
	
container-attach:
	devcontainer exec --workspace-folder . bash

# Lint + type-check (check-only). CI runs this too.
check:
	uv run ruff check
	uv run ty check

# Auto-format and apply safe fixes in place. Run manually when you want it;
# the first run will reformat the whole codebase.
format:
	uv run ruff format
	uv run ruff check --fix

build: check
	uv build

# Run the pytest unit-test suite (pure-logic tests; no infra access).
test:
	uv run pytest

# ── DOCS ──────────────────────────────────────────────────────────────────────

# Write the JSON Schema, the config reference and the command reference into
# docs/. The output is git-ignored: CI runs this before building, so there is no
# committed copy to keep in sync. Both recipes below depend on it, because the
# nav references those pages and --strict fails when they are missing.
docs-gen:
	uv run python docs/gen_docs.py

# Live-preview the docs site at http://127.0.0.1:8000
docs-serve: docs-gen
	uv run --group docs mkdocs serve

# Build the static site into site/ (what CI deploys).
docs-build: docs-gen
	uv run --group docs mkdocs build --strict

local-install:
	pipx install --force $(ls -t dist/*.whl | head -n1) --force

install-ansible-collection:
	uv run ansible-galaxy collection install -r ansible/requirements.yml
