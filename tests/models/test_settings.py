"""Tests for models/input_conf/settings.py — Settings and Dns validation.

The proxy models live in models/input_conf/proxy.py; see test_proxy.py.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.settings import Dns, Settings


def _creds(tmp_ssh_key: Path) -> dict[str, Any]:
    return {"username": "u", "ssh_key_path": str(tmp_ssh_key)}


# ── Settings ──────────────────────────────────────────────────────────────────


def test_settings_creds_only_is_valid(tmp_ssh_key: Path) -> None:
    s = Settings.model_validate({"default_creds": _creds(tmp_ssh_key)})
    assert s.dns is None
    assert s.proxy is None


def test_settings_requires_default_creds() -> None:
    with pytest.raises(ValidationError, match="default_creds"):
        Settings.model_validate({})


def test_settings_env_file_defaults_none(tmp_ssh_key: Path) -> None:
    s = Settings.model_validate({"default_creds": _creds(tmp_ssh_key)})
    assert s.env_file is None


def test_settings_accepts_env_file(tmp_ssh_key: Path) -> None:
    s = Settings.model_validate(
        {"default_creds": _creds(tmp_ssh_key), "env_file": "secrets.env"}
    )
    assert s.env_file == "secrets.env"


def test_settings_with_dns_and_proxy(tmp_ssh_key: Path) -> None:
    data: dict[str, Any] = {
        "default_creds": _creds(tmp_ssh_key),
        "dns": {"local_dns_suffix": "home.local", "pihole_location": "10.0.0.53"},
        "proxy": {
            "proxy_suffix": "home.arpa",
            "tls": {"provider": "cloudflare"},
            "access_lists": {"local": {"default": True, "accept": ["10.0.0.0/24"]}},
        },
    }
    s = Settings.model_validate(data)
    assert s.dns is not None and s.dns.local_dns_suffix == "home.local"
    assert s.proxy is not None and s.proxy.proxy_suffix == "home.arpa"


def test_settings_rejects_unknown_field(tmp_ssh_key: Path) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Settings.model_validate({"default_creds": _creds(tmp_ssh_key), "oops": True})


# ── Dns ───────────────────────────────────────────────────────────────────────


def test_dns_valid() -> None:
    dns = Dns.model_validate(
        {"local_dns_suffix": "home.local", "pihole_location": "10.0.0.53"}
    )
    assert dns.local_dns_suffix == "home.local"


def test_dns_requires_local_dns_suffix() -> None:
    with pytest.raises(ValidationError, match="local_dns_suffix"):
        Dns.model_validate({"pihole_location": "10.0.0.53"})


def test_dns_requires_pihole_location() -> None:
    with pytest.raises(ValidationError, match="pihole_location"):
        Dns.model_validate({"local_dns_suffix": "home.local"})


def test_dns_rejects_invalid_ip() -> None:
    with pytest.raises(ValidationError):
        Dns.model_validate(
            {"local_dns_suffix": "home.local", "pihole_location": "not-an-ip"}
        )
