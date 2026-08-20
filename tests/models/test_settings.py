"""Tests for models/input_conf/settings.py — the Settings container.

The blocks it holds have their own modules and their own tests: proxy.py /
test_proxy.py, dns.py / test_dns.py, select.py / test_select.py. What is left
here is Settings itself.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.settings import Settings


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


def test_settings_accepts_env_file(tmp_ssh_key: Path, tmp_path: Path) -> None:
    env = tmp_path / "secrets.env"
    env.write_text("")
    s = Settings.model_validate(
        {"default_creds": _creds(tmp_ssh_key), "env_file": str(env)}
    )
    assert s.env_file == env


def test_settings_with_dns_and_proxy(tmp_ssh_key: Path) -> None:
    data: dict[str, Any] = {
        "default_creds": _creds(tmp_ssh_key),
        "dns": {"suffix": "home.local", "pihole": {"target": "pihole"}},
        "proxy": {
            "proxy_suffix": "home.arpa",
            "tls": {"provider": "cloudflare"},
            "default_access": "local",
            "access_lists": {"local": {"accept": ["10.0.0.0/24"]}},
        },
    }
    s = Settings.model_validate(data)
    assert s.dns is not None and s.dns.suffix == "home.local"
    assert s.proxy is not None and s.proxy.proxy_suffix == "home.arpa"


def test_settings_rejects_unknown_field(tmp_ssh_key: Path) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Settings.model_validate({"default_creds": _creds(tmp_ssh_key), "oops": True})
