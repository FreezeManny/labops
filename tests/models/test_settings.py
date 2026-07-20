"""Tests for models/input_conf/settings.py — Settings, Dns, and Proxy validation."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.settings import AccessList, Dns, Proxy, Settings


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
        "proxy": {
            "proxy_suffix": "home.arpa",
            "proxy_location": "10.0.0.80",
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


def _proxy(**overrides: object) -> dict[str, Any]:
    data: dict[str, Any] = {
        "proxy_suffix": "home.arpa",
        "proxy_location": "10.0.0.80",
        "access_lists": {"local": {"default": True, "accept": ["10.0.0.0/24"]}},
    }
    data.update(overrides)
    return data


def test_proxy_valid() -> None:
    proxy = Proxy.model_validate(_proxy())
    assert proxy.proxy_suffix == "home.arpa"
    assert proxy.default_access_list == "local"


def test_proxy_requires_proxy_suffix() -> None:
    data = _proxy()
    del data["proxy_suffix"]
    with pytest.raises(ValidationError, match="proxy_suffix"):
        Proxy.model_validate(data)


def test_proxy_requires_proxy_location() -> None:
    data = _proxy()
    del data["proxy_location"]
    with pytest.raises(ValidationError, match="proxy_location"):
        Proxy.model_validate(data)


def test_proxy_rejects_invalid_ip() -> None:
    with pytest.raises(ValidationError):
        Proxy.model_validate(_proxy(proxy_location="not-an-ip"))


def test_proxy_requires_access_lists() -> None:
    with pytest.raises(ValidationError, match="access_lists"):
        Proxy.model_validate({"proxy_suffix": "home.arpa", "proxy_location": "10.0.0.80"})


def test_proxy_requires_a_default_list() -> None:
    with pytest.raises(ValidationError, match="exactly one list as 'default: true'"):
        Proxy.model_validate(_proxy(access_lists={"vpn": {"accept": ["100.64.0.0/10"]}}))


def test_proxy_rejects_multiple_defaults() -> None:
    with pytest.raises(ValidationError, match="only one access list may be 'default"):
        Proxy.model_validate(_proxy(access_lists={
            "a": {"default": True, "accept": ["10.0.0.0/24"]},
            "b": {"default": True, "accept": ["10.0.1.0/24"]},
        }))


def test_proxy_rejects_bad_cidr() -> None:
    with pytest.raises(ValidationError):
        Proxy.model_validate(_proxy(access_lists={"local": {"default": True, "accept": ["not-a-cidr"]}}))


# ── AccessList ──────────────────────────────────────────────────────────────


def test_access_list_accept_only() -> None:
    al = AccessList.model_validate({"accept": ["10.0.0.0/24"]})
    assert al.default is False and al.deny is None


def test_access_list_accept_with_deny_carveout() -> None:
    al = AccessList.model_validate({"accept": ["10.0.0.0/24"], "deny": ["10.0.0.66/32"]})
    assert al.accept is not None and al.deny is not None


def test_access_list_requires_accept() -> None:
    # deny-only (no accept) is rejected — accept is mandatory.
    with pytest.raises(ValidationError, match="accept"):
        AccessList.model_validate({"deny": ["10.0.0.66/32"]})


def test_access_list_rejects_empty_accept() -> None:
    with pytest.raises(ValidationError, match="at least one 'accept' CIDR"):
        AccessList.model_validate({"accept": []})
