"""Tests for path resolution via ``context={"base_dir": ...}``."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.docker import StackEntry
from models.input_conf.proxy import Proxy
from models.input_conf.creds import Creds
from models.input_conf.settings import Settings


# ── base_dir context wins over the cwd ────────────────────────────────────────


def test_config_path_resolves_against_base_dir(tmp_path: Path) -> None:
    (tmp_path / "stacks" / "caddy").mkdir(parents=True)
    entry = StackEntry.model_validate(
        {"config_path": "stacks/caddy"},
        context={"base_dir": tmp_path},
    )
    assert entry.config_path == (tmp_path / "stacks" / "caddy")


def test_template_resolves_against_base_dir(tmp_path: Path) -> None:
    tpl = tmp_path / "custom.j2"
    tpl.write_text("# custom\n")
    proxy_data: dict[str, Any] = {
        "proxy_suffix": ".test",
        "template": "custom.j2",
        "default_access": "all",
        "access_lists": {"all": {"accept": ["0.0.0.0/0"]}},
    }
    proxy = Proxy.model_validate(proxy_data, context={"base_dir": tmp_path})
    assert proxy.template is not None
    assert proxy.template == tpl


def test_ssh_key_path_resolves_against_base_dir(tmp_path: Path) -> None:
    key = tmp_path / "keys" / "id_ed25519"
    key.parent.mkdir()
    key.write_text("FAKE")
    creds = Creds.model_validate(
        {"username": "u", "ssh_key_path": "keys/id_ed25519"},
        context={"base_dir": tmp_path},
    )
    assert creds.ssh_key_path == key


def test_env_file_resolves_against_base_dir(tmp_path: Path) -> None:
    env = tmp_path / "secrets" / "prod.env"
    env.parent.mkdir()
    env.write_text("")
    key = tmp_path / "id"
    key.write_text("FAKE")
    s = Settings.model_validate(
        {
            "default_creds": {"username": "u", "ssh_key_path": str(key)},
            "env_file": "secrets/prod.env",
        },
        context={"base_dir": tmp_path},
    )
    assert s.env_file == env


# ── env_file existence check ──────────────────────────────────────────────────


def test_explicit_env_file_must_exist(tmp_path: Path) -> None:
    key = tmp_path / "id"
    key.write_text("FAKE")
    with pytest.raises(ValidationError, match="env_file"):
        Settings.model_validate(
            {
                "default_creds": {"username": "u", "ssh_key_path": str(key)},
                "env_file": str(tmp_path / "nonexistent.env"),
            },
        )


def test_omitted_env_file_is_fine(tmp_path: Path) -> None:
    key = tmp_path / "id"
    key.write_text("FAKE")
    s = Settings.model_validate(
        {"default_creds": {"username": "u", "ssh_key_path": str(key)}},
    )
    assert s.env_file is None
