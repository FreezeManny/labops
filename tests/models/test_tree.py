"""Tests for the Walk half of models.nodes — the single config-tree traversal.

Everything that walks the config (uniqueness validators, every finder) goes
through YamlRoot.iter_nodes / iter_web_services, so the guarantees asserted here
— reaching every depth, the path and parent attached to each node, and where a
docker stack's services are considered to live — are relied on repo-wide.
"""

from pathlib import Path
from typing import Any

import pytest

from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.vm import VM
from models.input_conf.yaml_root import YamlRoot


@pytest.fixture
def nested(valid_config_dict: dict[str, Any], tmp_docker_dir: Path) -> YamlRoot:
    """valid_config_dict plus a second level: an LXC and a VM under vm1.

    Base shape (from conftest): host prox -> lxc ct1, vm vm1 (docker stack app);
    hosts edge and nas, each with one web_service.
    """
    vm1 = valid_config_dict["hosts"]["prox"]["vm"]["vm1"]
    vm1["lxc"] = {
        "deep-ct": {
            "os": "alpine",
            "ip": "10.0.0.10",
            "vmid": 301,
            "web_services": [{"port": 8443, "proxy_name": "deepweb"}],
        }
    }
    vm1["vm"] = {"deep-vm": {"os": "debian", "ip": "10.0.0.11", "vmid": 302}}
    return YamlRoot.model_validate(valid_config_dict)


# ─── iter_nodes ───────────────────────────────────────────────────────────────


def test_reaches_every_node_at_every_depth(nested: YamlRoot) -> None:
    names = {ref.node.name for ref in nested.iter_nodes()}
    assert names == {"prox", "ct1", "vm1", "deep-ct", "deep-vm", "edge", "nas"}


def test_hosts_are_yielded_too(nested: YamlRoot) -> None:
    # Not just their children — validate_unique_ips relies on hosts being walked.
    hosts = [ref.node.name for ref in nested.iter_nodes() if isinstance(ref.node, Host)]
    assert set(hosts) == {"prox", "edge", "nas"}


def test_path_records_the_route_from_the_root(nested: YamlRoot) -> None:
    paths = {ref.node.name: ref.path for ref in nested.iter_nodes()}
    assert paths["prox"] == ["prox"]
    assert paths["vm1"] == ["prox", "vm1"]
    assert paths["deep-ct"] == ["prox", "vm1", "deep-ct"]
    assert paths["deep-vm"] == ["prox", "vm1", "deep-vm"]


def test_parent_is_the_containing_node(nested: YamlRoot) -> None:
    parents = {
        ref.node.name: (ref.parent.name if ref.parent else None)
        for ref in nested.iter_nodes()
    }
    assert parents["prox"] is None  # a top-level host has no parent
    assert parents["ct1"] == "prox"
    assert parents["deep-ct"] == "vm1"  # not the host at the top of the tree
    assert parents["deep-vm"] == "vm1"


def test_nodes_are_yielded_before_their_children(nested: YamlRoot) -> None:
    order = [ref.node.name for ref in nested.iter_nodes()]
    assert order.index("prox") < order.index("vm1") < order.index("deep-ct")


def test_lxcs_are_leaves(nested: YamlRoot) -> None:
    lxcs = [ref for ref in nested.iter_nodes() if isinstance(ref.node, LXC)]
    assert {r.node.name for r in lxcs} == {"ct1", "deep-ct"}


def test_vms_at_any_depth(nested: YamlRoot) -> None:
    vms = [ref for ref in nested.iter_nodes() if isinstance(ref.node, VM)]
    assert {r.node.name for r in vms} == {"vm1", "deep-vm"}


def test_config_without_hosts_yields_nothing(
    valid_config_dict: dict[str, Any],
) -> None:
    del valid_config_dict["hosts"]
    # web_services are gone with the hosts, so settings.proxy has nothing to route.
    model = YamlRoot.model_validate(valid_config_dict)
    assert list(model.iter_nodes()) == []
    assert list(model.iter_web_services()) == []


# ─── iter_web_services ────────────────────────────────────────────────────────


def test_collects_services_from_nodes_and_stacks(nested: YamlRoot) -> None:
    names = {ref.web_service.proxy_name for ref in nested.iter_web_services()}
    # ct1web/edge/nas sit on nodes; app is inside vm1's docker stack; deepweb is
    # two levels down.
    assert names == {"ct1web", "app", "edge", "nas", "deepweb"}


def test_node_is_where_the_service_is_reached(nested: YamlRoot) -> None:
    by_name = {r.web_service.proxy_name: r for r in nested.iter_web_services()}
    # A docker stack's services are published on the docker host's own address,
    # so the upstream is vm1's IP, not something belonging to the stack.
    assert str(by_name["app"].node.ip) == "10.0.0.3"
    assert by_name["app"].node.name == "vm1"


def test_stack_is_attached_only_to_stack_services(nested: YamlRoot) -> None:
    by_name = {r.web_service.proxy_name: r for r in nested.iter_web_services()}
    assert by_name["app"].stack is not None
    assert by_name["app"].stack.name == "app"
    assert by_name["ct1web"].stack is None  # declared directly on the node


def test_stack_name_is_not_a_path_segment(nested: YamlRoot) -> None:
    by_name = {r.web_service.proxy_name: r for r in nested.iter_web_services()}
    # The path locates the *node*; a stack is not addressable in the tree.
    assert by_name["app"].path == ["prox", "vm1"]
    assert by_name["deepweb"].path == ["prox", "vm1", "deep-ct"]


def test_services_without_a_proxy_name_are_still_yielded(
    valid_config_dict: dict[str, Any],
) -> None:
    # Routing skips them, but the port-collision and access checks must not.
    valid_config_dict["hosts"]["edge"]["web_services"].append({"port": 8081})
    model = YamlRoot.model_validate(valid_config_dict)
    ports = [
        r.web_service.port
        for r in model.iter_web_services()
        if r.web_service.proxy_name is None
    ]
    assert ports == [8081]
