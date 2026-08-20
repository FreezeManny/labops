"""Tests for models/input_conf/yaml_root.py — the cross-resource validators.

These recursive validators are the core safety net: a duplicate IP / name /
proxy_name across deeply nested hosts→vm→lxc trees would silently mis-target
real infrastructure.
"""

from pathlib import Path
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


# ── settings.dns.pihole names something that exists ───────────────────────────
#
# Same reasoning as settings.proxy.deploy.target: written once, read months later,
# and nothing between load and `dns sync` ever looks at it. Checkable here because
# `target:` resolves through find_node and nothing else — which only became true
# once an off-config address stopped being a valid answer, since a typo and a
# deliberate bare IP were previously the same string.


def _with_pihole(cfg: dict[str, Any], **pihole: object) -> YamlRoot:
    cfg["settings"]["dns"] = {"suffix": ".lab", "pihole": pihole}
    return YamlRoot.model_validate(cfg)


def test_pihole_target_naming_a_node_validates(
    valid_config_dict: dict[str, Any],
) -> None:
    assert _with_pihole(valid_config_dict, target="edge").settings.dns is not None


def test_pihole_target_may_be_an_ip(valid_config_dict: dict[str, Any]) -> None:
    assert _with_pihole(valid_config_dict, target="10.0.0.2").settings.dns is not None


def test_unknown_pihole_target_rejected_at_load(
    valid_config_dict: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError, match="settings.dns.pihole.target"):
        _with_pihole(valid_config_dict, target="nope")


def test_a_vmid_is_not_a_pihole_target(valid_config_dict: dict[str, Any]) -> None:
    """A vmid names a guest only together with its parent, so it names none here."""
    with pytest.raises(ValidationError, match="settings.dns.pihole.target"):
        _with_pihole(valid_config_dict, target="101")  # ct1's vmid


def test_an_off_config_address_is_rejected_at_load(
    valid_config_dict: dict[str, Any],
) -> None:
    """The route for a Pi-hole labops does not manage is `os: unmanaged`, which
    keeps it inside the uniqueness and DNS-label checks instead of outside them."""
    with pytest.raises(ValidationError, match="os: unmanaged"):
        _with_pihole(valid_config_dict, target="10.0.0.99")


def test_unknown_docker_stack_rejected_at_load(
    valid_config_dict: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError, match="matches no docker stack"):
        _with_pihole(valid_config_dict, docker_stack="nope")


def test_a_docker_stack_on_several_nodes_rejected_at_load(
    valid_config_dict: dict[str, Any], tmp_docker_dir: Path
) -> None:
    valid_config_dict["hosts"]["edge"]["docker"] = {
        "root_path": "/srv",
        "stacks": {"app": {"config_path": str(tmp_docker_dir)}},
    }
    with pytest.raises(ValidationError, match="exists in multiple locations"):
        _with_pihole(valid_config_dict, docker_stack="app")


def test_a_known_docker_stack_validates(valid_config_dict: dict[str, Any]) -> None:
    assert _with_pihole(valid_config_dict, docker_stack="app").settings.dns is not None


def test_no_server_block_is_not_checked(valid_config_dict: dict[str, Any]) -> None:
    """Records without a publisher is a legitimate state, so there is nothing to
    resolve — and `dns list` must keep working offline."""
    valid_config_dict["settings"]["dns"] = {"suffix": ".lab"}
    assert YamlRoot.model_validate(valid_config_dict).settings.dns is not None
