"""Tests for src.proxy.tls_warnings — DNS-provider token sanity checks.

The warnings only read local sources (an inline token and the .env secret store),
so each test writes a temp config-dir + .env and points tls_warnings at it.
"""

from pathlib import Path
from typing import Any

from models.input_conf.yaml_root import YamlRoot
from src.proxy import tls_warnings


def _model(cfg: dict[str, Any], tls: dict[str, str] | None) -> YamlRoot:
    if tls is None:
        cfg["settings"]["proxy"].pop("tls", None)
    else:
        cfg["settings"]["proxy"]["tls"] = tls
    return YamlRoot.model_validate(cfg)


def _cfg_path(tmp_path: Path, env_contents: str | None) -> Path:
    if env_contents is not None:
        (tmp_path / ".env").write_text(env_contents)
    return tmp_path / "homelab.yml"


def test_warns_when_no_token_anywhere(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    model = _model(valid_config_dict, {"provider": "cloudflare"})
    warns = tls_warnings(model, _cfg_path(tmp_path, None))  # no .env at all
    assert len(warns) == 1
    # Provider-neutral wording; the env var (from the registry) identifies which
    # provider's credential is missing.
    assert "no TLS token" in warns[0]
    assert "CF_API_TOKEN" in warns[0]


def test_no_warning_when_env_has_token(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    model = _model(valid_config_dict, {"provider": "cloudflare"})
    assert tls_warnings(model, _cfg_path(tmp_path, "CF_API_TOKEN=abc")) == []


def test_warns_when_inline_matches_env(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    # Agreeing with the .env does not make an inline token safe — it is still
    # rendered in clear text into the Caddyfile.
    model = _model(valid_config_dict, {"provider": "cloudflare", "token": "abc"})
    warns = tls_warnings(model, _cfg_path(tmp_path, "CF_API_TOKEN=abc"))
    assert len(warns) == 1
    assert "clear text" in warns[0]


def test_warns_when_inline_differs_from_env(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    model = _model(valid_config_dict, {"provider": "cloudflare", "token": "abc"})
    warns = tls_warnings(model, _cfg_path(tmp_path, "CF_API_TOKEN=different"))
    # The clear-text warning plus the disagreement warning.
    assert len(warns) == 2
    assert "clear text" in warns[0]
    assert "differs" in warns[1]


def test_warns_with_inline_token_and_no_env(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    model = _model(valid_config_dict, {"provider": "cloudflare", "token": "abc"})
    warns = tls_warnings(model, _cfg_path(tmp_path, None))
    # No "missing token" warning — it is present, just in the wrong place.
    assert len(warns) == 1
    assert "clear text" in warns[0]
    assert "CF_API_TOKEN" in warns[0]


def test_inline_token_warning_does_not_leak_the_token(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    model = _model(valid_config_dict, {"provider": "cloudflare", "token": "s3cret"})
    warns = tls_warnings(model, _cfg_path(tmp_path, None))
    assert all("s3cret" not in w for w in warns)


def test_no_warning_when_provider_none(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    model = _model(valid_config_dict, {"provider": "none"})
    assert tls_warnings(model, _cfg_path(tmp_path, None)) == []


def test_no_warning_without_tls(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    model = _model(valid_config_dict, None)
    assert tls_warnings(model, _cfg_path(tmp_path, None)) == []
