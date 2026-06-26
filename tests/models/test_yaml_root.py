"""Tests for models/input_conf/yaml_root.py — the cross-resource validators.

These recursive validators are the core safety net: a duplicate IP / name /
proxy_name across deeply nested hosts→vm→lxc trees would silently mis-target
real infrastructure.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.yaml_root import YamlRoot


def test_valid_config_validates(valid_config_dict: dict[str, Any]) -> None:
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None
    assert set(model.hosts) == {"prox", "edge"}


def test_propagate_host_and_unmanaged_names(valid_config_dict: dict[str, Any]) -> None:
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None
    assert model.hosts["prox"].name == "prox"
    assert model.hosts["edge"].name == "edge"
    assert model.unmanaged is not None
    assert model.unmanaged["nas"].name == "nas"


def test_duplicate_ip_host_vs_nested_lxc(valid_config_dict: dict[str, Any]) -> None:
    # Reuse the lxc IP on the unmanaged node.
    valid_config_dict["unmanaged"]["nas"]["ip"] = "10.0.0.2"
    with pytest.raises(ValidationError, match="Duplicate IP address"):
        YamlRoot.model_validate(valid_config_dict)


def test_duplicate_ip_across_nested_vm(valid_config_dict: dict[str, Any]) -> None:
    # vm1 (10.0.0.3) collides with the bare-metal host edge.
    valid_config_dict["hosts"]["edge"]["ip"] = "10.0.0.3"
    with pytest.raises(ValidationError, match="Duplicate IP address"):
        YamlRoot.model_validate(valid_config_dict)


def test_duplicate_name_host_vs_lxc(valid_config_dict: dict[str, Any]) -> None:
    # Rename the lxc to collide with a host key.
    valid_config_dict["hosts"]["prox"]["lxc"]["edge"] = (
        valid_config_dict["hosts"]["prox"]["lxc"].pop("ct1")
    )
    with pytest.raises(ValidationError, match="Duplicate name"):
        YamlRoot.model_validate(valid_config_dict)


def test_duplicate_name_unmanaged_vs_vm(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["unmanaged"]["vm1"] = valid_config_dict["unmanaged"].pop("nas")
    with pytest.raises(ValidationError, match="Duplicate name"):
        YamlRoot.model_validate(valid_config_dict)


def test_duplicate_proxy_name_web_service_vs_docker_stack(
    valid_config_dict: dict[str, Any],
) -> None:
    # edge's web_service proxy_name collides with the docker stack's proxy_name.
    valid_config_dict["hosts"]["edge"]["web_services"][0]["proxy_name"] = "app"
    with pytest.raises(ValidationError, match="Duplicate proxy_name"):
        YamlRoot.model_validate(valid_config_dict)


def test_unknown_top_level_field_rejected(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["bogus"] = True
    with pytest.raises(ValidationError):
        YamlRoot.model_validate(valid_config_dict)
