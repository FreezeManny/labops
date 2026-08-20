"""Tests for src/wake/find.py — resolving the node to wake, and ``--list``.

Unlike the per-kind finders this one matches across hosts, VMs and LXCs at once,
so the cases that matter are the ones where the kinds meet: which identifiers name
a node regardless of its kind, and at what depth.

A node id is a name or an IP, and nothing else. vmid is deliberately not one — it
is unique only per Proxmox node, so it identifies a guest only together with its
parent. Ambiguity, which this module used to have to refuse to guess at, cannot
arise any more: ``YamlRoot.validate_unique_names`` and ``validate_unique_ips``
span the whole tree, at every depth, so at most one node can ever match.

Error convention: ``NodeNotFound`` — a ValueError — for no match, which
src/cli/wake.py renders as one line.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.vm import VM
from models.input_conf.yaml_root import YamlRoot
from models.nodes import NodeNotFound, NodeRef
from src.wake import resolve_wake_target, wakeable


def _nest_under_vm1(cfg: dict[str, Any], name: str, vmid: int) -> dict[str, Any]:
    """Add an LXC at depth 2 — deeper than any per-parent check reaches."""
    cfg["hosts"]["prox"]["vm"]["vm1"]["hypervisor"] = "proxmox"
    cfg["hosts"]["prox"]["vm"]["vm1"]["lxc"] = {
        name: {"os": "alpine", "ip": "10.0.0.9", "vmid": vmid},
    }
    return cfg


# ── Resolving ─────────────────────────────────────────────────────────────────


def test_a_bare_metal_host_resolves_by_name(wake_config: YamlRoot) -> None:
    ref: NodeRef = resolve_wake_target(wake_config, "nas")
    assert isinstance(ref.node, Host)
    assert ref.path == ["nas"]
    assert ref.parent is None  # a top-level host has nothing above it


def test_a_guest_carries_its_parent(wake_config: YamlRoot) -> None:
    """The guest path needs it: qm/pct start runs on the parent, not the guest."""
    ref: NodeRef = resolve_wake_target(wake_config, "ct1")
    assert isinstance(ref.node, LXC)
    assert ref.parent is not None and ref.parent.name == "prox"
    assert ref.path == ["prox", "ct1"]


def test_a_node_resolves_by_ip(wake_config: YamlRoot) -> None:
    assert resolve_wake_target(wake_config, "10.0.0.3").node.name == "vm1"


def test_a_guest_does_not_resolve_by_vmid(wake_config: YamlRoot) -> None:
    """vmid is not a node id: unique per Proxmox node, so it names a guest only
    together with its parent. ct1 and vm1 are reachable by name and IP instead."""
    for vmid in ("101", "201"):
        with pytest.raises(NodeNotFound):
            resolve_wake_target(wake_config, vmid)


def test_a_host_resolves_by_its_own_ip(wake_config: YamlRoot) -> None:
    ref: NodeRef = resolve_wake_target(wake_config, "10.0.0.1")
    assert isinstance(ref.node, Host) and ref.node.name == "prox"


def test_an_unknown_target_raises(wake_config: YamlRoot) -> None:
    with pytest.raises(NodeNotFound) as excinfo:
        resolve_wake_target(wake_config, "nope")
    assert "nope" in str(excinfo.value)


# ── Depth and uniqueness ──────────────────────────────────────────────────────


def test_a_name_reused_deeper_in_the_tree_is_rejected_at_load(
    wake_config_dict: dict[str, Any],
) -> None:
    """The finder never has to choose, because this config does not load.

    The check spans the whole tree, so nesting the duplicate two levels down does
    not slip past it — and the error names both claimants by their full path.
    """
    cfg = _nest_under_vm1(wake_config_dict, "ct1", 301)

    with pytest.raises(ValidationError) as excinfo:
        YamlRoot.model_validate(cfg)

    message = str(excinfo.value)
    assert "Duplicate name" in message
    assert "prox → ct1" in message and "prox → vm1 → ct1" in message


def test_a_vmid_reused_deeper_in_the_tree_still_loads(
    wake_config_dict: dict[str, Any],
) -> None:
    """A duplicate vmid is legal — which is exactly why it is not an identifier."""
    cfg = _nest_under_vm1(wake_config_dict, "other", 101)
    config: YamlRoot = YamlRoot.model_validate(cfg)

    with pytest.raises(NodeNotFound):
        resolve_wake_target(config, "101")


def test_a_deeply_nested_node_resolves_by_ip(
    wake_config_dict: dict[str, Any],
) -> None:
    """Depth is not a limit on resolution — only on nothing at all."""
    cfg = _nest_under_vm1(wake_config_dict, "deep-ct", 301)
    config: YamlRoot = YamlRoot.model_validate(cfg)
    assert resolve_wake_target(config, "10.0.0.9").path == ["prox", "vm1", "deep-ct"]


# ── wake --list ───────────────────────────────────────────────────────────────


def test_wakeable_lists_only_nodes_with_a_mac(wake_config: YamlRoot) -> None:
    assert [ref.node.name for ref in wakeable(wake_config)] == ["ct1", "nas"]


def test_wakeable_reports_the_normalised_mac(wake_config: YamlRoot) -> None:
    macs = {ref.node.name: ref.node.mac for ref in wakeable(wake_config)}
    assert macs == {"ct1": "aa:bb:cc:dd:ee:02", "nas": "aa:bb:cc:dd:ee:01"}


def test_wakeable_is_empty_when_no_node_has_a_mac(
    valid_config_dict: dict[str, Any],
) -> None:
    assert wakeable(YamlRoot.model_validate(valid_config_dict)) == []


def test_wakeable_follows_tree_order(wake_config_dict: dict[str, Any]) -> None:
    """Pre-order, VMs before LXCs — the listing order, not a per-command accident."""
    wake_config_dict["hosts"]["prox"]["mac"] = "aa:bb:cc:dd:ee:03"
    wake_config_dict["hosts"]["prox"]["vm"]["vm1"]["mac"] = "aa:bb:cc:dd:ee:04"
    config = YamlRoot.model_validate(wake_config_dict)

    refs: list[NodeRef] = wakeable(config)
    assert [ref.node.name for ref in refs] == ["prox", "vm1", "ct1", "nas"]
    assert isinstance(refs[1].node, VM) and isinstance(refs[2].node, LXC)
