"""Tests for src/dns/location.py — what settings.dns.pihole_location may name.

One field, three shapes, and the two DNS commands want different things from it, so
this is where they are pinned down. ``dns sync`` only ever needs ``address``;
``dns upgrade`` needs to know *which* shape matched, because a stack and a bare
address are both reasons to refuse.

In ``valid_config_dict``: proxmox host ``prox`` (10.0.0.1) holds lxc ``ct1``
(10.0.0.2, vmid 101) and vm ``vm1`` (10.0.0.3, running the docker stack ``app``);
bare-metal ``edge`` is 10.0.0.4 and ``nas`` is 10.0.0.5.
"""

from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot
from src.dns import PiholeLocation, resolve_location


def _resolve(cfg: dict[str, Any], location: str) -> PiholeLocation:
    cfg["settings"]["dns"]["pihole_location"] = location
    config: YamlRoot = YamlRoot.model_validate(cfg)
    assert config.settings.dns is not None
    return resolve_location(config, config.settings.dns)


# ── A config node ─────────────────────────────────────────────────────────────


def test_node_by_name(dns_config_dict: dict[str, Any]) -> None:
    found = _resolve(dns_config_dict, "edge")
    assert found.address == "10.0.0.4"
    assert found.node is not None
    assert found.stack is None
    assert not found.is_stack


def test_node_by_ip(dns_config_dict: dict[str, Any]) -> None:
    found = _resolve(dns_config_dict, "10.0.0.2")
    assert found.address == "10.0.0.2"
    assert found.node is not None


def test_a_vmid_is_not_a_node_id(dns_config_dict: dict[str, Any]) -> None:
    """A vmid names a guest only per Proxmox node, so it is not accepted here.

    It falls through the node lookup like any other unknown string and is reported
    against every shape the setting does accept.
    """
    with pytest.raises(ValueError, match="matches no host, VM, LXC or docker stack"):
        _resolve(dns_config_dict, "101")  # ct1's vmid


def test_unmanaged_node_still_resolves(dns_config_dict: dict[str, Any]) -> None:
    # Resolution does not judge; `dns upgrade` is what refuses an unmanaged node,
    # and records to it are perfectly legitimate.
    found = _resolve(dns_config_dict, "nas")
    assert found.address == "10.0.0.5"
    assert found.node is not None


# ── A docker stack ────────────────────────────────────────────────────────────


def test_stack_resolves_to_its_host_node_address(
    dns_config_dict: dict[str, Any],
) -> None:
    # A stack's services are published on the node's own address — the same rule
    # the proxy uses, which is why the stack name is not part of the address.
    found = _resolve(dns_config_dict, "app")
    assert found.address == "10.0.0.3"  # vm1, which runs the stack
    assert found.is_stack
    assert found.node is None


def test_stack_reports_where_it_runs(dns_config_dict: dict[str, Any]) -> None:
    # Used in the `dns upgrade` refusal, so it has to name something recognisable.
    assert _resolve(dns_config_dict, "app").where == "prox → vm1"


# ── A bare address ────────────────────────────────────────────────────────────


def test_off_config_ip_is_used_verbatim(dns_config_dict: dict[str, Any]) -> None:
    # A Pi-hole labops does not otherwise manage: records work, and nothing is
    # invented about how to reach it over SSH.
    found = _resolve(dns_config_dict, "10.0.0.99")
    assert found.address == "10.0.0.99"
    assert found.node is None
    assert found.stack is None


# ── Failures ──────────────────────────────────────────────────────────────────


def test_unknown_name_lists_every_accepted_shape(
    dns_config_dict: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="matches no host, VM, LXC or docker stack"):
        _resolve(dns_config_dict, "nope")


def test_a_name_that_is_both_node_and_stack_is_ambiguous(
    dns_config_dict: dict[str, Any],
) -> None:
    # Silently preferring one would send `dns upgrade` somewhere the user did not
    # mean — to a host instead of refusing over a container, or the reverse.
    dns_config_dict["hosts"]["app"] = {
        "type": "bare-metal",
        "os": "debian",
        "ip": "10.0.0.7",
    }
    with pytest.raises(ValueError, match="is ambiguous"):
        _resolve(dns_config_dict, "app")


def test_unset_location_is_reported_clearly(dns_config_dict: dict[str, Any]) -> None:
    # Not a config-validation error: deriving records is useful on its own, so this
    # only bites when something actually needs to reach a Pi-hole.
    del dns_config_dict["settings"]["dns"]["pihole_location"]
    config = YamlRoot.model_validate(dns_config_dict)
    assert config.settings.dns is not None
    with pytest.raises(ValueError, match="is not set"):
        resolve_location(config, config.settings.dns)


def test_unset_location_points_at_dns_list(dns_config_dict: dict[str, Any]) -> None:
    del dns_config_dict["settings"]["dns"]["pihole_location"]
    config = YamlRoot.model_validate(dns_config_dict)
    assert config.settings.dns is not None
    with pytest.raises(ValueError, match="dns list. works without it"):
        resolve_location(config, config.settings.dns)
