"""Tests for models/input_conf/creds.py — auth-method exclusion and ~ expansion."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from models.input_conf.creds import Creds


def test_ssh_key_only_is_valid(tmp_ssh_key: Path) -> None:
    creds = Creds.model_validate({"username": "u", "ssh_key_path": str(tmp_ssh_key)})
    assert creds.passwd is None
    assert creds.ssh_key_path == tmp_ssh_key


def test_password_only_is_valid() -> None:
    creds = Creds.model_validate({"username": "u", "passwd": "secret"})
    assert creds.passwd == "secret"
    assert creds.ssh_key_path is None


def test_both_passwd_and_key_rejected(tmp_ssh_key: Path) -> None:
    with pytest.raises(ValidationError, match="Cannot set both"):
        Creds.model_validate(
            {"username": "u", "passwd": "secret", "ssh_key_path": str(tmp_ssh_key)}
        )


def test_neither_passwd_nor_key_rejected() -> None:
    with pytest.raises(ValidationError, match="Must set either"):
        Creds.model_validate({"username": "u"})


def test_expand_tilde_resolves_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Point $HOME at a temp dir holding the key, then reference it via "~".
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "key").write_text("FAKE KEY")

    creds = Creds.model_validate({"username": "u", "ssh_key_path": "~/key"})

    assert creds.ssh_key_path == Path(os.path.expanduser("~/key"))
    assert "~" not in str(creds.ssh_key_path)


def test_missing_key_file_rejected(tmp_path: Path) -> None:
    # FilePath requires the file to exist.
    with pytest.raises(ValidationError):
        Creds.model_validate(
            {"username": "u", "ssh_key_path": str(tmp_path / "does-not-exist")}
        )
