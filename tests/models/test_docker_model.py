"""Tests for models/input_conf/docker.py — path resolution and name propagation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

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


def test_relative_root_path_rejected(tmp_docker_dir: Path) -> None:
    # Resolved on the node, so a relative value would land in whatever directory
    # SSH logged into. Same rule as settings.proxy.deploy.caddyfile_dest.
    with pytest.raises(ValidationError, match="must be an absolute path"):
        Docker.model_validate(
            {
                "root_path": "srv/stacks",
                "stacks": {"caddy": {"config_path": str(tmp_docker_dir)}},
            }
        )


def test_absolute_root_path_keeps_its_trailing_slash(tmp_docker_dir: Path) -> None:
    # Tolerated, not normalised: src/docker/common.py rstrips it when building
    # compose_dest, and stripping it here would be a second place to keep in step.
    docker = Docker.model_validate(
        {
            "root_path": "/srv/",
            "stacks": {"caddy": {"config_path": str(tmp_docker_dir)}},
        }
    )
    assert docker.root_path == "/srv/"
