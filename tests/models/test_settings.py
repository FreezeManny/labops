"""Tests for models/input_conf/settings.py — Settings, Dns, and Proxy validation."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.settings import Dns, Proxy, Settings


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


def test_settings_with_dns_and_proxy(tmp_ssh_key: Path) -> None:
    data: dict[str, Any] = {
        "default_creds": _creds(tmp_ssh_key),
        "dns": {"local_dns_suffix": "home.local", "pihole_location": "10.0.0.53"},
        "proxy": {"proxy_suffix": "home.arpa", "proxy_location": "10.0.0.80"},
    }
    s = Settings.model_validate(data)
    assert s.dns is not None and s.dns.local_dns_suffix == "home.local"
    assert s.proxy is not None and s.proxy.proxy_suffix == "home.arpa"


def test_settings_rejects_unknown_field(tmp_ssh_key: Path) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Settings.model_validate({"default_creds": _creds(tmp_ssh_key), "oops": True})


# ── Dns ───────────────────────────────────────────────────────────────────────


def test_dns_valid() -> None:
    dns = Dns.model_validate({"local_dns_suffix": "home.local", "pihole_location": "10.0.0.53"})
    assert dns.local_dns_suffix == "home.local"


def test_dns_requires_local_dns_suffix() -> None:
    with pytest.raises(ValidationError, match="local_dns_suffix"):
        Dns.model_validate({"pihole_location": "10.0.0.53"})


def test_dns_requires_pihole_location() -> None:
    with pytest.raises(ValidationError, match="pihole_location"):
        Dns.model_validate({"local_dns_suffix": "home.local"})


def test_dns_rejects_invalid_ip() -> None:
    with pytest.raises(ValidationError):
        Dns.model_validate({"local_dns_suffix": "home.local", "pihole_location": "not-an-ip"})


# ── Proxy ─────────────────────────────────────────────────────────────────────


def test_proxy_valid() -> None:
    proxy = Proxy.model_validate({"proxy_suffix": "home.arpa", "proxy_location": "10.0.0.80"})
    assert proxy.proxy_suffix == "home.arpa"


def test_proxy_requires_proxy_suffix() -> None:
    with pytest.raises(ValidationError, match="proxy_suffix"):
        Proxy.model_validate({"proxy_location": "10.0.0.80"})


def test_proxy_requires_proxy_location() -> None:
    with pytest.raises(ValidationError, match="proxy_location"):
        Proxy.model_validate({"proxy_suffix": "home.arpa"})


def test_proxy_rejects_invalid_ip() -> None:
    with pytest.raises(ValidationError):
        Proxy.model_validate({"proxy_suffix": "home.arpa", "proxy_location": "not-an-ip"})
