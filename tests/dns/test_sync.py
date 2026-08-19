"""Tests for src/dns/sync.py — where the API password comes from, and what is
warned about. The network paths are covered in test_cli.py via stubbed targets.
"""

from pathlib import Path
from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
from src.dns import dns_warnings, require_dns, resolve_password


def _model(cfg: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(cfg)


# ─── require_dns ──────────────────────────────────────────────────────────────


def test_require_dns_returns_the_block(dns_config_dict: dict[str, Any]) -> None:
    assert require_dns(_model(dns_config_dict)).suffix == "lab"


def test_require_dns_raises_without_settings(valid_config_dict: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="settings.dns is not configured"):
        require_dns(_model(valid_config_dict))


# ─── pihole_location ──────────────────────────────────────────────────────────


def test_single_address(dns_config_dict: dict[str, Any]) -> None:
    assert str(require_dns(_model(dns_config_dict)).pihole_location) == "10.0.0.53"


def test_a_list_of_addresses_is_rejected(dns_config_dict: dict[str, Any]) -> None:
    # Only one instance is supported: the secret store holds a single
    # PIHOLE_PASSWORD, so a list would assume they share one API password.
    dns_config_dict["settings"]["dns"]["pihole_location"] = ["10.0.0.53", "10.0.0.54"]
    with pytest.raises(ValueError):
        _model(dns_config_dict)


# ─── suffix normalization ─────────────────────────────────────────────────────


@pytest.mark.parametrize("configured,expected", [(".lab", "lab"), ("lab", "lab")])
def test_suffix_strips_a_leading_dot(
    dns_config_dict: dict[str, Any], configured: str, expected: str
) -> None:
    dns_config_dict["settings"]["dns"]["local_dns_suffix"] = configured
    assert require_dns(_model(dns_config_dict)).suffix == expected


# ─── resolve_password ─────────────────────────────────────────────────────────


def test_password_read_from_the_env_store(
    dns_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("PIHOLE_PASSWORD=from-env\n")
    config_path: Path = tmp_path / "homelab.yml"
    assert resolve_password(_model(dns_config_dict), config_path) == "from-env"


def test_inline_password_wins(dns_config_dict: dict[str, Any], tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PIHOLE_PASSWORD=from-env\n")
    dns_config_dict["settings"]["dns"]["password"] = "inline"
    config_path: Path = tmp_path / "homelab.yml"
    assert resolve_password(_model(dns_config_dict), config_path) == "inline"


def test_missing_password_raises_with_the_env_path(
    dns_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    config_path: Path = tmp_path / "homelab.yml"
    with pytest.raises(ValueError, match="PIHOLE_PASSWORD is not set"):
        resolve_password(_model(dns_config_dict), config_path)


def test_custom_env_file_is_honoured(
    dns_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    (tmp_path / "secrets.env").write_text("PIHOLE_PASSWORD=elsewhere\n")
    dns_config_dict["settings"]["env_file"] = "secrets.env"
    config_path: Path = tmp_path / "homelab.yml"
    model = YamlRoot.model_validate(dns_config_dict, context={"base_dir": tmp_path})
    assert resolve_password(model, config_path) == "elsewhere"


# ─── dns_warnings ─────────────────────────────────────────────────────────────


def test_inline_password_warns(dns_config_dict: dict[str, Any], tmp_path: Path) -> None:
    dns_config_dict["settings"]["dns"]["password"] = "inline"
    warnings = dns_warnings(_model(dns_config_dict), tmp_path / "homelab.yml")
    assert len(warnings) == 1
    assert "clear text" in warnings[0]


def test_env_store_password_does_not_warn(
    dns_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("PIHOLE_PASSWORD=from-env\n")
    assert dns_warnings(_model(dns_config_dict), tmp_path / "homelab.yml") == []


def test_no_dns_settings_does_not_warn(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    assert dns_warnings(_model(valid_config_dict), tmp_path / "homelab.yml") == []
