"""Tests for the `proxy access` CLI command."""

from pathlib import Path
from typing import Any

from typer.testing import CliRunner
from typer.testing import Result

from models.input_conf.yaml_root import YamlRoot
from src.cli.core import console, state
from src.cli.proxy import app

runner = CliRunner()


def _load_model(cfg: dict[str, Any]) -> None:
    state.model = YamlRoot.model_validate(cfg)


def _invoke(*args: str) -> Result:
    # Widen the shared console so Rich doesn't truncate table cells.
    old_width = console.width
    console.width = 300
    try:
        return runner.invoke(app, list(args))
    finally:
        console.width = old_width


def test_access_shows_default_list(valid_config_dict: dict[str, Any]) -> None:
    """Services with no explicit access show the default list marked '(default)'."""
    _load_model(valid_config_dict)

    result = _invoke("access")

    assert result.exit_code == 0, result.output
    assert "local (default)" in result.output
    assert "10.0.0.0/24" in result.output


def test_access_multi_list_union(valid_config_dict: dict[str, Any]) -> None:
    """A service referencing multiple lists shows the union of their CIDRs."""
    valid_config_dict["settings"]["proxy"]["access_lists"]["vpn"] = {
        "accept": ["100.64.0.0/10"],
    }
    valid_config_dict["hosts"]["edge"]["web_services"] = [
        {"port": 80, "proxy_name": "edge", "access": ["local", "vpn"]},
    ]
    _load_model(valid_config_dict)

    result = _invoke("access")

    assert result.exit_code == 0, result.output
    assert "local, vpn" in result.output
    assert "10.0.0.0/24" in result.output
    assert "100.64.0.0/10" in result.output


def test_access_no_deny_shows_dash(valid_config_dict: dict[str, Any]) -> None:
    """When an access list carries no deny, the Deny column renders as '—'."""
    _load_model(valid_config_dict)

    result = _invoke("access")

    assert result.exit_code == 0, result.output
    assert "—" in result.output


def test_access_deny_shown(valid_config_dict: dict[str, Any]) -> None:
    """When an access list carries a deny, its CIDRs appear in the output."""
    valid_config_dict["settings"]["proxy"]["access_lists"]["local"]["deny"] = [
        "10.0.0.66/32",
    ]
    _load_model(valid_config_dict)

    result = _invoke("access")

    assert result.exit_code == 0, result.output
    assert "10.0.0.66/32" in result.output


def test_access_proxy_not_configured(tmp_ssh_key: Path) -> None:
    """Exit with an error when settings.proxy is missing entirely."""
    state.model = YamlRoot.model_validate(
        {
            "settings": {
                "default_creds": {
                    "username": "ansible",
                    "ssh_key_path": str(tmp_ssh_key),
                },
            },
            "hosts": {
                "h": {
                    "hypervisor": "none",
                    "os": "debian",
                    "ip": "10.0.0.1",
                },
            },
        }
    )

    result = _invoke("access")

    assert result.exit_code == 1
    assert "settings.proxy is not configured" in result.output
