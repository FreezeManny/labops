"""Tests for src/dns/location.py — resolving a ``target`` / ``docker_stack`` block.

Nothing here is Pi-hole's: this is the lookup any backend's location block uses,
so it is exercised through the generic ``resolve_service_location``.

The two keys are the point. Which one the user wrote decides *what kind of thing*
the answer is, and that is the one fact an address cannot carry — a container and
an installation answer at the same IP. So a name is never tried against both
shapes, and the two cases come back as different types rather than one type with
two optional halves.

In ``valid_config_dict``: proxmox host ``prox`` (10.0.0.1) holds lxc ``ct1``
(10.0.0.2, vmid 101) and vm ``vm1`` (10.0.0.3, running the docker stack ``app``);
bare-metal ``edge`` is 10.0.0.4 and ``nas`` is 10.0.0.5 with ``os: unmanaged``.
"""

from pathlib import Path
from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
from models.nodes import NodeNotFound
from src.dns.location import (
    NodeLocation,
    ServiceLocation,
    StackLocation,
    resolve_service_location,
)

SETTING = "settings.dns.pihole"


def _resolve(cfg: dict[str, Any], **keys: str) -> ServiceLocation:
    config: YamlRoot = YamlRoot.model_validate(cfg)
    return resolve_service_location(config, setting=SETTING, **keys)


# ── target: a node in this config ─────────────────────────────────────────────


def test_a_target_resolves_to_the_node_and_its_address(
    valid_config_dict: dict[str, Any],
) -> None:
    found = _resolve(valid_config_dict, target="edge")
    assert isinstance(found, NodeLocation)
    assert found.address == "10.0.0.4"
    assert found.node.node.name == "edge"
    assert not found.is_stack


def test_a_target_may_be_given_as_an_ip(valid_config_dict: dict[str, Any]) -> None:
    """The same field works either way round, so nothing has to be renamed."""
    found = _resolve(valid_config_dict, target="10.0.0.2")
    assert isinstance(found, NodeLocation)
    assert found.node.node.name == "ct1"


def test_a_nested_guest_resolves(valid_config_dict: dict[str, Any]) -> None:
    assert _resolve(valid_config_dict, target="ct1").address == "10.0.0.2"


def test_an_unmanaged_node_resolves(valid_config_dict: dict[str, Any]) -> None:
    """Resolution does not judge — records to an unmanaged box are legitimate.

    `dns upgrade` is what refuses it, and it refuses on the node's os rather than
    on anything decided here.
    """
    found = _resolve(valid_config_dict, target="nas")
    assert isinstance(found, NodeLocation)
    assert found.address == "10.0.0.5"


def test_the_setting_names_the_key_the_user_wrote(
    valid_config_dict: dict[str, Any],
) -> None:
    """So a message quotes `…pihole.target`, not the block it sits in."""
    assert _resolve(valid_config_dict, target="edge").setting == f"{SETTING}.target"


def test_where_is_the_target_as_written(valid_config_dict: dict[str, Any]) -> None:
    assert _resolve(valid_config_dict, target="edge").where == "edge"


# ── docker_stack: a container on a node ───────────────────────────────────────


def test_a_stack_resolves_to_its_host_node_address(
    valid_config_dict: dict[str, Any],
) -> None:
    """A stack's services are published on the node's address — as the proxy does,
    which is why the stack name is not part of the address."""
    found = _resolve(valid_config_dict, docker_stack="app")
    assert isinstance(found, StackLocation)
    assert found.address == "10.0.0.3"  # vm1, which runs it
    assert found.is_stack


def test_a_stack_reports_where_it_runs(valid_config_dict: dict[str, Any]) -> None:
    """Used in the `dns upgrade` refusal, so it must name something recognisable."""
    assert _resolve(valid_config_dict, docker_stack="app").where == "prox → vm1"


def test_the_stack_setting_names_its_own_key(
    valid_config_dict: dict[str, Any],
) -> None:
    found = _resolve(valid_config_dict, docker_stack="app")
    assert found.setting == f"{SETTING}.docker_stack"


# ── the two cases are different types ─────────────────────────────────────────


def test_neither_case_carries_the_other_s_field() -> None:
    """The discriminator is the type, so no caller needs an assertion to narrow."""
    assert not hasattr(NodeLocation, "stack")
    assert not hasattr(StackLocation, "node")


def test_a_name_that_is_both_a_node_and_a_stack_is_not_a_problem(
    valid_config_dict: dict[str, Any],
) -> None:
    """It used to be ambiguous. Now the key you wrote says which you meant.

    This is the whole reason the block has two keys instead of one string: labops
    never has to guess, so the same name can legitimately be both.
    """
    valid_config_dict["hosts"]["app"] = {
        "type": "bare-metal",
        "os": "debian",
        "ip": "10.0.0.7",
    }
    as_node = _resolve(valid_config_dict, target="app")
    as_stack = _resolve(valid_config_dict, docker_stack="app")

    assert isinstance(as_node, NodeLocation) and as_node.address == "10.0.0.7"
    assert isinstance(as_stack, StackLocation) and as_stack.address == "10.0.0.3"


# ── failures ──────────────────────────────────────────────────────────────────


def test_an_unknown_target_is_a_miss_not_a_fallthrough_to_the_stacks(
    valid_config_dict: dict[str, Any],
) -> None:
    """`app` is a real stack; asked for as a target it must still miss."""
    with pytest.raises(NodeNotFound):
        _resolve(valid_config_dict, target="app")


def test_a_missing_target_points_at_the_route_for_an_unmanaged_box(
    valid_config_dict: dict[str, Any],
) -> None:
    """An off-config address used to resolve here, which made a typo and a
    deliberate address indistinguishable. `os: unmanaged` is the route now, so the
    miss carries it."""
    with pytest.raises(NodeNotFound, match="os: unmanaged"):
        _resolve(valid_config_dict, target="10.0.0.99")


def test_a_vmid_is_not_a_node_id(valid_config_dict: dict[str, Any]) -> None:
    """A vmid names a guest only together with its parent, so it names none here."""
    with pytest.raises(NodeNotFound):
        _resolve(valid_config_dict, target="101")  # ct1's vmid


def test_an_unknown_stack_says_where_stacks_are_declared(
    valid_config_dict: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="matches no docker stack"):
        _resolve(valid_config_dict, docker_stack="nope")


def test_a_stack_on_several_nodes_is_not_specific_enough(
    valid_config_dict: dict[str, Any], tmp_docker_dir: Path
) -> None:
    """Distinct from the miss above: that name is wrong, this one is not precise.

    The same compose stack on two nodes is an ordinary thing to declare, so it is
    only an error for a caller that needs exactly one of them.
    """
    valid_config_dict["hosts"]["edge"]["docker"] = {
        "root_path": "/srv",
        "stacks": {"app": {"config_path": str(tmp_docker_dir)}},
    }
    with pytest.raises(ValueError, match="exists in multiple locations"):
        _resolve(valid_config_dict, docker_stack="app")


def test_neither_key_is_a_bug_in_the_caller_s_model(
    valid_config_dict: dict[str, Any],
) -> None:
    """The block's own validator normally prevents this from being reachable."""
    with pytest.raises(ValueError, match="names no location"):
        _resolve(valid_config_dict)
