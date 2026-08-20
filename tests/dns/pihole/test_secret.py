"""Tests for src/dns/pihole/secret.py — where the API password comes from, and
when labops says something about it.

Both warnings are about the same secret being somewhere it need not be: at rest
in a file that is usually committed, and in flight across the LAN. Neither is
fatal — a working setup is a working setup — so what is asserted here is that
they are *said*, and that a properly configured instance stays quiet.
"""

from pathlib import Path
from typing import Any

import pytest

from models.input_conf.pihole import Pihole
from models.input_conf.yaml_root import YamlRoot
from src.dns.pihole.secret import pihole_warnings, resolve_password


@pytest.fixture
def config(valid_config_dict: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(valid_config_dict)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "homelab.yml"


def _pihole(**overrides: object) -> Pihole:
    data: dict[str, Any] = {"target": "edge"}
    data.update(overrides)
    return Pihole.model_validate(data)


# ── resolving the password ────────────────────────────────────────────────────


def test_an_inline_password_is_used_as_given(
    config: YamlRoot, config_path: Path
) -> None:
    assert resolve_password(config, config_path, _pihole(password="hunter2")) == (
        "hunter2"
    )


def test_the_secret_store_is_read_when_nothing_is_inline(
    config: YamlRoot, config_path: Path
) -> None:
    (config_path.parent / ".env").write_text("PIHOLE_PASSWORD=from-the-store\n")
    assert resolve_password(config, config_path, _pihole()) == "from-the-store"


def test_no_password_anywhere_names_both_places_to_put_one(
    config: YamlRoot, config_path: Path
) -> None:
    with pytest.raises(ValueError, match="PIHOLE_PASSWORD"):
        resolve_password(config, config_path, _pihole())


def test_an_inline_password_wins_over_the_store(
    config: YamlRoot, config_path: Path
) -> None:
    """Explicit beats ambient, even though the store is the better place."""
    (config_path.parent / ".env").write_text("PIHOLE_PASSWORD=from-the-store\n")
    assert resolve_password(config, config_path, _pihole(password="inline")) == "inline"


# ── warnings ──────────────────────────────────────────────────────────────────


def test_https_with_the_password_in_the_store_warns_about_nothing(
    config: YamlRoot, config_path: Path
) -> None:
    assert pihole_warnings(config, config_path, _pihole()) == []


def test_an_inline_password_is_reported_with_the_file_to_move_it_to(
    config: YamlRoot, config_path: Path
) -> None:
    warnings = pihole_warnings(config, config_path, _pihole(password="hunter2"))
    assert len(warnings) == 1
    assert "clear text in your config file" in warnings[0]
    assert str(config_path.parent / ".env") in warnings[0]


def test_http_is_reported_because_it_sends_the_password_in_clear_text(
    config: YamlRoot, config_path: Path
) -> None:
    warnings = pihole_warnings(config, config_path, _pihole(scheme="http"))
    assert len(warnings) == 1
    assert "clear text" in warnings[0]
    assert "settings.dns.pihole.scheme" in warnings[0]


def test_the_http_warning_does_not_oversell_https(
    config: YamlRoot, config_path: Path
) -> None:
    """labops skips certificate verification, so https is not end-to-end trust."""
    warning = pihole_warnings(config, config_path, _pihole(scheme="http"))[0]
    assert "machine-in-the-middle" in warning


def test_both_exposures_are_reported_separately(
    config: YamlRoot, config_path: Path
) -> None:
    """One fix does not imply the other; a user may have made only one mistake."""
    warnings = pihole_warnings(
        config, config_path, _pihole(scheme="http", password="hunter2")
    )
    assert len(warnings) == 2
