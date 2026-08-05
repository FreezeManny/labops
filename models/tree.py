"""Walking the config tree.

A homelab config is a tree: hosts contain VMs and LXCs, VMs contain more of
both, and any node may carry web_services and docker stacks. Almost everything
labops does starts by walking that tree — validating uniqueness across it,
resolving a target by name, collecting every route or stack.

Each of those used to carry its own recursive walker, which meant the shape of
the tree was re-derived (and quietly disagreed about) in seven places. It lives
here instead, and ``YamlRoot.iter_nodes`` / ``YamlRoot.iter_web_services`` are
how callers reach it.

Traversal is depth-first and pre-order — a node is yielded before its children,
and VMs before LXCs at each level. Callers that care about ordering (the CLI
listings) get one consistent order rather than a per-command accident.

The one traversal deliberately left out is
``common_validators.web_services.check_duplicate_ws_ports``: it runs *during*
Host/VM/LXC validation, so importing this module from it would close an import
cycle (host -> common_validators -> tree -> host). It walks a single node rather
than the tree, so it duplicates little.
"""

from dataclasses import dataclass
from typing import Iterator, Mapping, Optional, Union

from models.input_conf.docker import StackEntry
from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.vm import VM
from models.input_conf.web_services import WebService

# Anything in the tree that has an ip, creds, web_services and docker.
Node = Union[Host, VM, LXC]

# Anything that can contain other nodes. LXCs cannot nest, so an LXC is never a
# parent; a top-level Host has no parent at all.
Parent = Union[Host, VM]


@dataclass(frozen=True)
class NodeRef:
    """A node together with where it sits in the tree."""

    node: Node
    parent: Optional[Parent]  # None only for a top-level host
    path: list[str]  # names from the root, e.g. ["cprox", "docker"]


@dataclass(frozen=True)
class WebServiceRef:
    """A web_service together with the node it is served from."""

    web_service: WebService
    node: Node  # where it is reached — node.ip is the upstream address
    stack: Optional[StackEntry]  # the docker stack it belongs to, if any
    # The *node's* path. A stack is not a path segment: its services are reached
    # at the docker host's own address, so the stack name would not locate them.
    path: list[str]


def _children(node: Node) -> Iterator[tuple[str, Node]]:
    """The nodes directly under ``node``, as (name, node) pairs."""
    if isinstance(node, LXC):
        return  # a container carries no nested nodes
    yield from (node.vm or {}).items()
    yield from (node.lxc or {}).items()


def _walk(node: Node, parent: Optional[Parent], path: list[str]) -> Iterator[NodeRef]:
    yield NodeRef(node=node, parent=parent, path=path)
    if isinstance(node, LXC):
        return
    for name, child in _children(node):
        yield from _walk(child, node, path + [name])


def iter_nodes(hosts: Optional[Mapping[str, Host]]) -> Iterator[NodeRef]:
    """Every host, VM and LXC in the config, at any depth."""
    for name, host in (hosts or {}).items():
        yield from _walk(host, None, [name])


def node_web_services(ref: NodeRef) -> Iterator[WebServiceRef]:
    """A single node's web_services: its own, then each docker stack's."""
    if ref.node.web_services:
        for ws in ref.node.web_services.root:
            yield WebServiceRef(
                web_service=ws, node=ref.node, stack=None, path=ref.path
            )
    if ref.node.docker:
        for stack in ref.node.docker.stacks.values():
            if not stack.web_services:
                continue
            for ws in stack.web_services.root:
                yield WebServiceRef(
                    web_service=ws, node=ref.node, stack=stack, path=ref.path
                )


def iter_web_services(hosts: Optional[Mapping[str, Host]]) -> Iterator[WebServiceRef]:
    """Every web_service in the config — each node's own and its stacks'."""
    for ref in iter_nodes(hosts):
        yield from node_web_services(ref)
