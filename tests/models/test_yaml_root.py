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
    assert set(model.hosts) == {"prox", "edge", "nas"}


def test_propagate_host_names(valid_config_dict: dict[str, Any]) -> None:
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None
    assert model.hosts["prox"].name == "prox"
    assert model.hosts["edge"].name == "edge"
    # nas is a normal host with os: unmanaged.
    assert model.hosts["nas"].name == "nas"
    assert model.hosts["nas"].os == "unmanaged"


def test_duplicate_ip_host_vs_nested_lxc(valid_config_dict: dict[str, Any]) -> None:
    # Reuse the lxc IP on the unmanaged (os) host nas.
    valid_config_dict["hosts"]["nas"]["ip"] = "10.0.0.2"
    with pytest.raises(ValidationError, match="Duplicate IP address"):
        YamlRoot.model_validate(valid_config_dict)


def test_duplicate_ip_across_nested_vm(valid_config_dict: dict[str, Any]) -> None:
    # vm1 (10.0.0.3) collides with the bare-metal host edge.
    valid_config_dict["hosts"]["edge"]["ip"] = "10.0.0.3"
    with pytest.raises(ValidationError, match="Duplicate IP address"):
        YamlRoot.model_validate(valid_config_dict)


def test_duplicate_name_host_vs_lxc(valid_config_dict: dict[str, Any]) -> None:
    # Rename the lxc to collide with a host key.
    valid_config_dict["hosts"]["prox"]["lxc"]["edge"] = valid_config_dict["hosts"][
        "prox"
    ]["lxc"].pop("ct1")
    with pytest.raises(ValidationError, match="Duplicate name"):
        YamlRoot.model_validate(valid_config_dict)


def test_duplicate_name_host_vs_vm(valid_config_dict: dict[str, Any]) -> None:
    # Rename the nas host to collide with the nested vm key "vm1".
    valid_config_dict["hosts"]["vm1"] = valid_config_dict["hosts"].pop("nas")
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


# ── Unmanaged-OS nodes participate in the cross-resource validators ────────────


def test_unmanaged_os_vm_in_tree_validates(valid_config_dict: dict[str, Any]) -> None:
    # A HAOS-style VM (os: unmanaged) under the proxmox host.
    valid_config_dict["hosts"]["prox"]["vm"]["haos"] = {
        "os": "unmanaged",
        "ip": "10.0.0.10",
        "vmid": 250,
        "web_services": [{"port": 8123, "proxy_name": "home"}],
    }
    model = YamlRoot.model_validate(valid_config_dict)
    assert model.hosts is not None
    prox_vms = model.hosts["prox"].vm
    assert prox_vms is not None
    haos = prox_vms["haos"]
    assert haos.os == "unmanaged"
    assert haos.name == "haos"


def test_unmanaged_os_node_ip_collision_rejected(
    valid_config_dict: dict[str, Any],
) -> None:
    # Collide the unmanaged VM's IP with the bare-metal host edge (10.0.0.4).
    valid_config_dict["hosts"]["prox"]["vm"]["haos"] = {
        "os": "unmanaged",
        "ip": "10.0.0.4",
        "vmid": 250,
    }
    with pytest.raises(ValidationError, match="Duplicate IP address"):
        YamlRoot.model_validate(valid_config_dict)


def test_unmanaged_os_node_proxy_name_collision_rejected(
    valid_config_dict: dict[str, Any],
) -> None:
    # Reuse the docker stack's proxy_name ("app") on the unmanaged VM.
    valid_config_dict["hosts"]["prox"]["vm"]["haos"] = {
        "os": "unmanaged",
        "ip": "10.0.0.10",
        "vmid": 250,
        "web_services": [{"port": 8123, "proxy_name": "app"}],
    }
    with pytest.raises(ValidationError, match="Duplicate proxy_name"):
        YamlRoot.model_validate(valid_config_dict)
