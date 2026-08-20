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
    ws = WebService.model_validate(
        {"port": 80, "proxy_name": "a", "access": ["local", "vpn"]}
    )
    assert ws.access == ["local", "vpn"]


# ── YamlRoot access-reference validation ────────────────────────────────────────


def test_known_access_list_is_accepted(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["settings"]["proxy"]["access_lists"]["open"] = {
        "accept": ["0.0.0.0/0"]
    }
    valid_config_dict["hosts"]["edge"]["web_services"][0]["access"] = ["open"]
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None


def test_unknown_access_list_rejected(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["hosts"]["edge"]["web_services"][0]["access"] = ["nope"]
    with pytest.raises(ValidationError, match="unknown access list 'nope'"):
        YamlRoot.model_validate(valid_config_dict)


def test_unknown_access_list_on_docker_stack_rejected(
    valid_config_dict: dict[str, Any],
) -> None:
    stack = valid_config_dict["hosts"]["prox"]["vm"]["vm1"]["docker"]["stacks"]["app"]
    stack["web_services"][0]["access"] = ["ghost"]
    with pytest.raises(ValidationError, match="unknown access list 'ghost'"):
        YamlRoot.model_validate(valid_config_dict)


def test_unknown_access_list_error_names_the_node(
    valid_config_dict: dict[str, Any],
) -> None:
    # proxy_name alone does not say where the service lives; the node path does.
    stack = valid_config_dict["hosts"]["prox"]["vm"]["vm1"]["docker"]["stacks"]["app"]
    stack["web_services"][0]["access"] = ["ghost"]
    with pytest.raises(ValidationError) as exc:
        YamlRoot.model_validate(valid_config_dict)
    assert "on 'prox → vm1'" in str(exc.value)


def test_multiple_lists_without_deny_accepted(
    valid_config_dict: dict[str, Any],
) -> None:
    lists = valid_config_dict["settings"]["proxy"]["access_lists"]
    lists["vpn"] = {"accept": ["100.64.0.0/10"]}
    valid_config_dict["hosts"]["edge"]["web_services"][0]["access"] = ["local", "vpn"]
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None


def test_multiple_lists_with_deny_rejected(valid_config_dict: dict[str, Any]) -> None:
    # `local`'s deny is a statement about the LAN; unioned onto the vpn range it
    # would become a ban on the tailscale route too.
    lists = valid_config_dict["settings"]["proxy"]["access_lists"]
    lists["local"]["deny"] = ["10.0.0.66/32"]
    lists["vpn"] = {"accept": ["100.64.0.0/10"]}
    valid_config_dict["hosts"]["edge"]["web_services"][0]["access"] = ["local", "vpn"]
    with pytest.raises(ValidationError) as exc:
        YamlRoot.model_validate(valid_config_dict)
    msg = str(exc.value)
    assert "'local' carries a 'deny'" in msg
    assert "web_service 'edge' on 'edge'" in msg
    assert "its own access list" in msg


def test_single_list_with_deny_accepted(valid_config_dict: dict[str, Any]) -> None:
    # One list is not a union, so its deny still means what it says.
    lists = valid_config_dict["settings"]["proxy"]["access_lists"]
    lists["local"]["deny"] = ["10.0.0.66/32"]
    valid_config_dict["hosts"]["edge"]["web_services"][0]["access"] = ["local"]
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None


def test_default_access_with_deny_accepted(valid_config_dict: dict[str, Any]) -> None:
    # default_access names a single list, so a deny on it is never unioned.
    lists = valid_config_dict["settings"]["proxy"]["access_lists"]
    lists["local"]["deny"] = ["10.0.0.66/32"]
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None


def test_web_services_without_proxy_rejected(valid_config_dict: dict[str, Any]) -> None:
    del valid_config_dict["settings"]["proxy"]
    with pytest.raises(ValidationError, match="settings.proxy is missing"):
        YamlRoot.model_validate(valid_config_dict)
