"""Tests for src.lxc.find / src.vm.find — nested nodes and ambiguous targets.

Both finders walk the config tree to any depth, mirroring src.proxy.find, so a
container or VM nested under a VM is addressable by every command that takes a
target. Depth used to mean a name or vmid could match more than one node, which
the finders had to refuse to guess at. Neither can happen now: YamlRoot makes
names unique across the whole tree, and vmid is no longer an identifier at all
(it is unique only per Proxmox node). So the cases asserted here are that a
duplicate name is rejected at *load* time, and that a vmid resolves nothing.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.yaml_root import YamlRoot
import src.lxc as lxc
import src.vm as vm


def _nested(cfg: dict[str, Any]) -> YamlRoot:
    """valid_config_dict, with an LXC and a VM hung off the existing vm1."""
    cfg["hosts"]["prox"]["vm"]["vm1"]["lxc"] = {
        "deep-ct": {"os": "alpine", "ip": "10.0.0.10", "vmid": 301},
    }
    cfg["hosts"]["prox"]["vm"]["vm1"]["vm"] = {
        "deep-vm": {"os": "debian", "ip": "10.0.0.11", "vmid": 302},
    }
    return YamlRoot.model_validate(cfg)


def _two_nodes_same_vmid(cfg: dict[str, Any]) -> YamlRoot:
    """A second Proxmox node whose container reuses vmid 101 (ct1's).

    Legal: Host.check_duplicate_vmid only enforces uniqueness within one node.
    """
    cfg["hosts"]["prox2"] = {
        "type": "proxmox",
        "os": "debian",
        "ip": "10.0.0.20",
        "lxc": {"ct2": {"os": "alpine", "ip": "10.0.0.21", "vmid": 101}},
    }
    return YamlRoot.model_validate(cfg)


# ─── LXC ──────────────────────────────────────────────────────────────────────


def test_findall_includes_lxc_nested_under_a_vm(
    valid_config_dict: dict[str, Any],
) -> None:
    names = [c.name for _, c in lxc.findAll(_nested(valid_config_dict))]
    assert set(names) == {"ct1", "deep-ct"}


def test_nested_lxc_is_addressable_by_name(valid_config_dict: dict[str, Any]) -> None:
    ((parent, container),) = lxc.find(_nested(valid_config_dict), ["deep-ct"])
    assert container.vmid == 301
    # The parent is the VM it lives in — that is what pct is run from, not the
    # Proxmox host at the top of the tree.
    assert parent.name == "vm1"
    assert str(parent.ip) == "10.0.0.3"


def test_nested_lxc_name_is_propagated(valid_config_dict: dict[str, Any]) -> None:
    # VM.propagate_lxc_vm_names — without it the name stays "" and the container
    # is unaddressable and unnamed in generated inventories.
    ((_, container),) = lxc.find(_nested(valid_config_dict), ["10.0.0.10"])
    assert container.name == "deep-ct"


def test_top_level_lxc_still_resolves_via_its_host(
    valid_config_dict: dict[str, Any],
) -> None:
    ((parent, container),) = lxc.find(_nested(valid_config_dict), ["ct1"])
    assert parent.name == "prox"
    assert container.vmid == 101


def test_a_duplicate_vmid_is_legal_and_matches_nothing(
    valid_config_dict: dict[str, Any],
) -> None:
    """The config loads — and the vmid names neither container, rather than one.

    This is why vmid was dropped as an identifier: it is unique only within one
    Proxmox node, so it could never name a guest on its own.
    """
    cfg = _two_nodes_same_vmid(valid_config_dict)
    with pytest.raises(KeyError, match="was not found"):
        lxc.find(cfg, ["101"])


def test_duplicate_vmid_still_addressable_by_name(
    valid_config_dict: dict[str, Any],
) -> None:
    cfg = _two_nodes_same_vmid(valid_config_dict)
    ((_, container),) = lxc.find(cfg, ["ct2"])
    assert str(container.ip) == "10.0.0.21"


def test_unknown_lxc_still_raises_keyerror(valid_config_dict: dict[str, Any]) -> None:
    with pytest.raises(KeyError, match="was not found"):
        lxc.find(YamlRoot.model_validate(valid_config_dict), ["nope"])


# ─── VM ───────────────────────────────────────────────────────────────────────


def test_findall_includes_vm_nested_under_a_vm(
    valid_config_dict: dict[str, Any],
) -> None:
    names = [v.name for v in vm.findAll(_nested(valid_config_dict))]
    assert set(names) == {"vm1", "deep-vm"}


def test_nested_vm_is_addressable_by_name(valid_config_dict: dict[str, Any]) -> None:
    (found,) = vm.find(_nested(valid_config_dict), ["deep-vm"])
    assert str(found.ip) == "10.0.0.11"


def test_nested_vm_is_addressable_by_ip(valid_config_dict: dict[str, Any]) -> None:
    (found,) = vm.find(_nested(valid_config_dict), ["10.0.0.11"])
    assert found.name == "deep-vm"


def test_duplicate_vm_name_across_depths_is_rejected_at_load(
    valid_config_dict: dict[str, Any],
) -> None:
    """validate_unique_names spans the whole tree, so a finder never sees two.

    The reused name is caught where the user can act on it — loading the config —
    rather than later, as an unresolvable target on whichever command happened to
    ask for it first.
    """
    valid_config_dict["hosts"]["prox"]["vm"]["vm1"]["vm"] = {
        "vm1": {"os": "debian", "ip": "10.0.0.12", "vmid": 303},
    }
    with pytest.raises(ValidationError, match="Duplicate name"):
        YamlRoot.model_validate(valid_config_dict)


def test_unknown_vm_still_raises_keyerror(valid_config_dict: dict[str, Any]) -> None:
    with pytest.raises(KeyError, match="was not found"):
        vm.find(YamlRoot.model_validate(valid_config_dict), ["nope"])
