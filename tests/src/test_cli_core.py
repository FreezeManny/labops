"""Tests for src/cli/core.py — config discovery and target resolution."""

from pathlib import Path
from typing import Any

import pytest
import typer

from models.input_conf.yaml_root import YamlRoot
from src.cli import core


# ─── find_config ────────────────────────────────────────────────────────────


def test_find_config_walks_up_to_parent(tmp_path: Path) -> None:
    (tmp_path / "homelab.yml").write_text("settings: {}")
    deep: Path = tmp_path / "a" / "b"
    deep.mkdir(parents=True)

    assert core.find_config(start=deep) == tmp_path / "homelab.yml"


def test_find_config_accepts_yaml_extension(tmp_path: Path) -> None:
    (tmp_path / "homelab.yaml").write_text("settings: {}")
    assert core.find_config(start=tmp_path) == tmp_path / "homelab.yaml"


def test_find_config_returns_none_when_absent(tmp_path: Path) -> None:
    deep: Path = tmp_path / "x" / "y"
    deep.mkdir(parents=True)
    # tmp_path has no homelab.{yml,yaml}; parents above are unlikely to either,
    # but guard by checking the walk from an isolated dir returns our None path.
    assert core.find_config(start=deep) is None


# ─── resolve_targets ────────────────────────────────────────────────────────


@pytest.fixture
def model(valid_config_dict: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(valid_config_dict)


def _finder(_: YamlRoot, targets: list[str]) -> list[str]:
    return ["found"] if targets == ["hit"] else []


def _finder_all_some(_: YamlRoot) -> list[str]:
    return ["a", "b"]


def _finder_all_empty(_: YamlRoot) -> list[str]:
    return []


def test_resolve_targets_by_name(model: YamlRoot) -> None:
    result = core.resolve_targets(
        model, "hit", False, _finder, _finder_all_some, "host"
    )
    assert result == ["found"]


def test_resolve_targets_missing_exits(model: YamlRoot) -> None:
    with pytest.raises(typer.Exit):
        core.resolve_targets(model, "miss", False, _finder, _finder_all_some, "host")


def test_resolve_targets_all(model: YamlRoot) -> None:
    result = core.resolve_targets(model, None, True, _finder, _finder_all_some, "host")
    assert result == ["a", "b"]


def test_resolve_targets_all_empty_exits(model: YamlRoot) -> None:
    with pytest.raises(typer.Exit):
        core.resolve_targets(model, None, True, _finder, _finder_all_empty, "host")


def test_resolve_targets_neither_exits(model: YamlRoot) -> None:
    with pytest.raises(typer.Exit):
        core.resolve_targets(model, None, False, _finder, _finder_all_some, "host")
