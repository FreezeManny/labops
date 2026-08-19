# Development

## Environment

The project uses [Dev Containers](https://containers.dev/) for a consistent
environment, and [uv](https://github.com/astral-sh/uv) for package management.

1. Open the project in VS Code (or any editor supporting Dev Containers).
2. **Reopen in Container** — this builds an environment with Python, Ansible and
   the CLI tooling already installed.
3. Sync dependencies and activate the virtual environment:

```bash
uv sync
source .venv/bin/activate
labops --help
```

Outside a dev container, `uv sync` is still all you need, plus
[just](https://github.com/casey/just) for the recipes below.

## Recipes

```bash
just check          # ruff lint + ty type-check   (CI runs this)
just format         # ruff format + safe fixes
just test           # pytest
just build          # check, then uv build
```

Ansible collections, when you need them locally:

```bash
just install-ansible-collection
```

## Documentation

Part of the docs is generated from the code by `docs/gen_docs.py`:

- `docs/labops.schema.json` — the config's JSON Schema, from the Pydantic models
- `docs/configuration/*.md` — the config reference, from that same schema
- `docs/commands/*.md` — the CLI reference, from Typer

**None of it is committed.** Those paths are git-ignored, and CI runs the
generator immediately before `mkdocs build`, so the reference cannot fall out of
date with the code it describes — there is no stored copy to go stale. Rename a
CLI flag and the next deploy simply describes the new one.

```bash
just docs-serve     # generate, then live preview at http://127.0.0.1:8000
just docs-build     # generate, then build the static site into site/
just docs-gen       # just the generation step, rarely needed on its own
```

Both site recipes generate first, because `mkdocs.yml`'s nav references those
pages and `--strict` fails when a page is missing.

Everything else under `docs/` is hand-written and tracked as normal.

!!! note "The generator lives in `docs/`"
    Beside the pages it produces, and deliberately not under `src/` or
    `models/` — those ship in the wheel (see `pyproject.toml`), and a docs
    generator has no business in a user's install. MkDocs copies it into the
    built site, which is harmless: the repository is public anyway.

### Where documentation lives

| Change | Where to write it |
| --- | --- |
| What a config key means | `Field(description=...)` on the model |
| What a block is for, or a rule spanning fields | The model's class docstring |
| What a command does | Its Typer docstring, with a `\b` examples block |
| How a subsystem fits together, and why | A guide under `docs/guides/` |

The first three end up in the generated reference *and* in `--help` / the JSON
Schema, so writing them once covers the terminal, the site and the user's editor.

### Writing command help

The bar is set by `src/cli/update.py` and `src/cli/wake.py`: a summary line, a
`[dim]` paragraph for real side effects and caveats, and a `\b` examples block on
anything that takes a target.

Rich markup is fine — `[bold]`, `[dim]` — because the generator converts it to
markdown. Do not turn off `rich_markup_mode` to make the docs cleaner; that would
fix the site by degrading the terminal.

## Releases

Releases are automated with
[release-please](https://github.com/googleapis/release-please). Commit messages
follow [Conventional Commits](https://www.conventionalcommits.org/) and a PR
title check enforces it.

- Merging to `main` updates a release PR with the changelog and version bump.
- Merging that PR tags the release.
- Publishing the release triggers the PyPI upload — the package is **not**
  published by hand.

To build the distribution files locally for testing:

```bash
uv build            # -> dist/*.whl and dist/*.tar.gz
just local-install  # pipx install the freshly built wheel
```

## Tests

```bash
uv run pytest
```

The suite is pure logic — no infrastructure access, no network — covering the
config models, the selectors, the finders and the render/plan steps. Anything
that would touch a real host is not tested here.
