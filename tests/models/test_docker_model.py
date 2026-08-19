"""Tests for models/input_conf/docker.py — path resolution and name propagation."""

from pathlib import Path

import pytest

from models.input_conf.docker import Docker, StackEntry


def test_resolve_config_path_makes_relative_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With no base_dir context, the cwd fallback resolves relative paths.
    (tmp_path / "caddy").mkdir()
    monkeypatch.chdir(tmp_path)

    entry = StackEntry.model_validate({"config_path": "./caddy"})

    assert entry.config_path.is_absolute()
    assert entry.config_path == (tmp_path / "caddy").resolve()


def test_propagate_stack_names(tmp_docker_dir: Path) -> None:
    docker = Docker.model_validate(
        {
            "root_path": "/srv",
            "stacks": {"caddy": {"config_path": str(tmp_docker_dir)}},
        }
    )
    assert docker.stacks["caddy"].name == "caddy"
