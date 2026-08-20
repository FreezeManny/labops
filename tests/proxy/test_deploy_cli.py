"""Tests for the `proxy sync` / `deploy` / `reload` CLI commands.

Their remaining run-time failure mode is a missing `settings.proxy.deploy` block,
which must read as a one-line error rather than a traceback. An unresolvable
target is no longer one of them: YamlRoot.validate_proxy_deploy_target rejects it
at load, so it is asserted here as a load-time error to pin down that the CLI can
no longer be reached with one. None of these tests reach ansible.
"""

from typing import Any

import pytest
from pydantic import ValidationError
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


def test_unknown_target_never_reaches_the_command(
    valid_config_dict: dict[str, Any],
) -> None:
    """The load fails, so no command runs with a target that resolves to nothing."""
    with pytest.raises(ValidationError, match="settings.proxy.deploy.target 'nope'"):
        _load(
            valid_config_dict,
            {"target": "nope", "caddyfile_dest": "/etc/caddy/Caddyfile"},
        )


def test_a_vmid_target_never_reaches_the_command(
    valid_config_dict: dict[str, Any],
) -> None:
    """A vmid is not a node id — unique only per Proxmox node, as prox2 shows here."""
    valid_config_dict["hosts"]["prox2"] = {
        "hypervisor": "proxmox",
        "os": "debian",
        "ip": "10.0.0.20",
        "lxc": {"ct2": {"os": "alpine", "ip": "10.0.0.21", "vmid": 101}},
    }

    with pytest.raises(ValidationError, match="settings.proxy.deploy.target '101'"):
        _load(
            valid_config_dict,
            {"target": "101", "caddyfile_dest": "/etc/caddy/Caddyfile"},
        )


@pytest.mark.parametrize("command", COMMANDS)
def test_missing_deploy_block_exits_cleanly(
    command: str, valid_config_dict: dict[str, Any]
) -> None:
    _load(valid_config_dict, None)  # proxy configured, but no deploy block

    result = runner.invoke(app, [command])

    assert result.exit_code == 1
    assert "settings.proxy.deploy is not configured" in result.output
