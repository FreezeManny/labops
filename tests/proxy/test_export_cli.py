"""Tests for the `proxy render` CLI command — printing, and writing with -o."""

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from models.input_conf.yaml_root import YamlRoot
from src.cli.core import state
from src.cli.proxy import app

runner = CliRunner()


def _load_model(cfg: dict[str, Any]) -> None:
    # The proxy sub-app reads state.model directly (the root callback that
    # normally populates it isn't in play when invoking the sub-app alone).
    state.model = YamlRoot.model_validate(cfg)


def test_render_prints_by_default(valid_config_dict: dict[str, Any]) -> None:
    _load_model(valid_config_dict)

    result = runner.invoke(app, ["render"])

    assert result.exit_code == 0, result.output
    assert "*.example.test {" in result.output


def test_render_output_writes_rendered_caddyfile(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    _load_model(valid_config_dict)
    dest: Path = tmp_path / "Caddyfile"

    result = runner.invoke(app, ["render", "-o", str(dest)])

    assert result.exit_code == 0, result.output
    assert dest.is_file()
    assert "*.example.test {" in dest.read_text()


def test_render_output_refuses_to_overwrite_without_force(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    _load_model(valid_config_dict)
    dest: Path = tmp_path / "Caddyfile"
    dest.write_text("keep me")

    result = runner.invoke(app, ["render", "--output", str(dest)])

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert dest.read_text() == "keep me"  # left untouched


def test_render_output_overwrites_with_force(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    _load_model(valid_config_dict)
    dest: Path = tmp_path / "Caddyfile"
    dest.write_text("old content")

    result = runner.invoke(app, ["render", "-o", str(dest), "--force"])

    assert result.exit_code == 0, result.output
    assert "*.example.test {" in dest.read_text()
