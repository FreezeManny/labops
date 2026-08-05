"""Tests for the `proxy sync` / `deploy` / `reload` CLI commands.

Their failure modes are config problems that only surface at run time — an
unresolvable or ambiguous deploy.target — and those must read as a one-line
error, not a traceback. None of these tests reach ansible: resolution fails
before a playbook is built.
"""

from typing import Any

import pytest
from typer.testing import CliRunner

from models.input_conf.yaml_root import YamlRoot
from src.cli.core import state
from src.cli.proxy import app

runner = CliRunner()

COMMANDS = ["sync", "deploy", "reload"]


def _load(cfg: dict[str, Any], deploy: dict[str, Any] | None) -> None:
    if deploy is not None:
        cfg["settings"]["proxy"]["deploy"] = deploy
    state.model = YamlRoot.model_validate(cfg)


@pytest.mark.parametrize("command", COMMANDS)
def test_unknown_target_exits_cleanly(
    command: str, valid_config_dict: dict[str, Any]
) -> None:
    _load(
        valid_config_dict,
        {"target": "nope", "caddyfile_dest": "/etc/caddy/Caddyfile"},
    )

    result = runner.invoke(app, [command])

    assert result.exit_code == 1
    assert "matches no host, VM or LXC" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", COMMANDS)
def test_ambiguous_target_exits_cleanly(
    command: str, valid_config_dict: dict[str, Any]
) -> None:
    # Two nodes, same vmid — legal config, unresolvable target.
    valid_config_dict["hosts"]["prox2"] = {
        "type": "proxmox",
        "os": "debian",
        "ip": "10.0.0.20",
        "lxc": {"ct2": {"os": "alpine", "ip": "10.0.0.21", "vmid": 101}},
    }
    _load(
        valid_config_dict,
        {"target": "101", "caddyfile_dest": "/etc/caddy/Caddyfile"},
    )

    result = runner.invoke(app, [command])

    assert result.exit_code == 1
    assert "ambiguous" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", COMMANDS)
def test_missing_deploy_block_exits_cleanly(
    command: str, valid_config_dict: dict[str, Any]
) -> None:
    _load(valid_config_dict, None)  # proxy configured, but no deploy block

    result = runner.invoke(app, [command])

    assert result.exit_code == 1
    assert "settings.proxy.deploy is not configured" in result.output
