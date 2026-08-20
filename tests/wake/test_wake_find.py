"""Tests for src/wake/find.py — resolving the node to wake, and ``--list``.

Unlike the per-kind finders this one matches across hosts, VMs and LXCs at once,
so the cases that matter are the ones where the kinds meet: a vmid that only
guests have, and a name that two nodes can legally share.

Ambiguity is built by nesting an LXC *under vm1*. ``YamlRoot.validate_unique_names``
and ``Host.check_duplicate_vmid`` only reach depth 1, so a name or vmid reused one
level deeper is valid config — and exactly the case the finder must refuse to guess
at rather than the one pydantic already rejects.

Error convention (from src/lxc/find.py, which src/cli/wake.py renders as one
line): KeyError for no match, ValueError for more than one.
"""

from typing import Any

import pytest

from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.vm import VM
from models.input_conf.yaml_root import YamlRoot
from models.nodes import NodeRef
from src.wake import resolve_wake_target, wakeable


def _nest_under_vm1(cfg: dict[str, Any], name: str, vmid: int) -> YamlRoot:
    """Add an LXC at depth 2, below every uniqueness check labops runs."""
    cfg["hosts"]["prox"]["vm"]["vm1"]["lxc"] = {
        name: {"os": "alpine", "ip": "10.0.0.9", "vmid": vmid},
    }
    return YamlRoot.model_validate(cfg)


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


def test_a_guest_resolves_by_vmid(wake_config: YamlRoot) -> None:
    assert resolve_wake_target(wake_config, "101").node.name == "ct1"
    assert resolve_wake_target(wake_config, "201").node.name == "vm1"


def test_a_hosts_ip_is_not_read_as_a_vmid(wake_config: YamlRoot) -> None:
    """A Host has no vmid, so the vmid branch must not be reached for one."""
    ref: NodeRef = resolve_wake_target(wake_config, "10.0.0.1")
    assert isinstance(ref.node, Host) and ref.node.name == "prox"


def test_an_unknown_target_raises_keyerror(wake_config: YamlRoot) -> None:
    with pytest.raises(KeyError) as excinfo:
        resolve_wake_target(wake_config, "nope")
    assert "nope" in excinfo.value.args[0]


def test_a_vmid_that_matches_nothing_raises_keyerror(wake_config: YamlRoot) -> None:
    with pytest.raises(KeyError):
        resolve_wake_target(wake_config, "999")


# ── Ambiguity ─────────────────────────────────────────────────────────────────


def test_a_name_reused_deeper_in_the_tree_is_ambiguous(
    wake_config_dict: dict[str, Any],
) -> None:
    config: YamlRoot = _nest_under_vm1(wake_config_dict, "ct1", 301)

    with pytest.raises(ValueError) as excinfo:
        resolve_wake_target(config, "ct1")

    message = str(excinfo.value)
    assert "ambiguous" in message
    assert "prox → ct1" in message and "prox → vm1 → ct1" in message
    assert "by IP" in message  # the way out


def test_a_vmid_reused_deeper_in_the_tree_is_ambiguous(
    wake_config_dict: dict[str, Any],
) -> None:
    config: YamlRoot = _nest_under_vm1(wake_config_dict, "other", 101)

    with pytest.raises(ValueError):
        resolve_wake_target(config, "101")


def test_an_ambiguous_name_still_resolves_by_ip(
    wake_config_dict: dict[str, Any],
) -> None:
    config: YamlRoot = _nest_under_vm1(wake_config_dict, "ct1", 301)
    assert resolve_wake_target(config, "10.0.0.9").path == ["prox", "vm1", "ct1"]


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
