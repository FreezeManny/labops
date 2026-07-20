"""Tests for the web_service `access` field and YamlRoot access-reference validation."""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.web_services import WebService
from models.input_conf.yaml_root import YamlRoot


# ── WebService.access coercion ─────────────────────────────────────────────────


def test_access_defaults_to_none() -> None:
    ws = WebService.model_validate({"port": 80, "proxy_name": "a"})
    assert ws.access is None


def test_access_bare_string_is_coerced_to_list() -> None:
    ws = WebService.model_validate({"port": 80, "proxy_name": "a", "access": "vpn"})
    assert ws.access == ["vpn"]


def test_access_list_preserved() -> None:
    ws = WebService.model_validate({"port": 80, "proxy_name": "a", "access": ["local", "vpn"]})
    assert ws.access == ["local", "vpn"]


# ── YamlRoot access-reference validation ────────────────────────────────────────


def test_known_access_list_is_accepted(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["settings"]["proxy"]["access_lists"]["open"] = {"accept": ["0.0.0.0/0"]}
    valid_config_dict["hosts"]["edge"]["web_services"][0]["access"] = ["open"]
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None


def test_unknown_access_list_rejected(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["hosts"]["edge"]["web_services"][0]["access"] = ["nope"]
    with pytest.raises(ValidationError, match="unknown access list 'nope'"):
        YamlRoot.model_validate(valid_config_dict)


def test_unknown_access_list_on_docker_stack_rejected(valid_config_dict: dict[str, Any]) -> None:
    stack = valid_config_dict["hosts"]["prox"]["vm"]["vm1"]["docker"]["stacks"]["app"]
    stack["web_services"][0]["access"] = ["ghost"]
    with pytest.raises(ValidationError, match="unknown access list 'ghost'"):
        YamlRoot.model_validate(valid_config_dict)


def test_web_services_without_proxy_rejected(valid_config_dict: dict[str, Any]) -> None:
    del valid_config_dict["settings"]["proxy"]
    with pytest.raises(ValidationError, match="settings.proxy is missing"):
        YamlRoot.model_validate(valid_config_dict)
