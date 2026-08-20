"""Questions about the config tree: walk it, find one node, select a subset.

A homelab config is a tree: hosts contain VMs and LXCs, VMs contain more of both,
and any node may carry web_services and docker stacks. Almost everything labops
does starts by asking the tree something — validating uniqueness across it,
resolving a named target, collecting every route or stack, picking what a command
acts on. All three shapes of that question live here:

* **Walk** — ``iter_nodes`` / ``iter_web_services``, the one depth-first traversal.
  Each of these used to carry its own recursive walker, which meant the shape of
  the tree was re-derived (and quietly disagreed about) in seven places.
* **Find** — ``node_matches`` / ``find_node``: does this string name this node, and
  which single node does it name. This too used to exist four times — in
  src/host/find.py, src/vm/find.py, src/lxc/find.py and src/wake/find.py — and the
  copies had drifted, each accepting a slightly different set of identifiers.
* **Select** — ``Selector`` / ``select_nodes``: which nodes match a set of criteria.
  Plural, and zero matches is a legitimate answer — that is what separates it from
  Find, where a miss is an error.

What is deliberately *not* here is how to reach a node once found. Credentials, the
pct-vs-ssh choice and Ansible host_vars live in src/utils/inventory.py, because
``models`` must not import ``src``.

Every entry point takes ``hosts`` rather than a ``YamlRoot``: settings.py imports
``Selector`` for its ``targets`` field, so depending on the root model here would
close a cycle. ``YamlRoot.iter_nodes`` / ``.select`` / ``.find_node`` are the front
doors.

Traversal is depth-first and pre-order — a node is yielded before its children, and
VMs before LXCs at each level. Callers that care about ordering (the CLI listings)
get one consistent order rather than a per-command accident.

The one traversal deliberately left out is
``common_validators.web_services.check_duplicate_ws_ports``: it runs *during*
Host/VM/LXC validation, so importing this module from it would close another cycle
(host -> common_validators -> nodes -> host). It walks a single node rather than the
tree, so it duplicates little.
"""

from dataclasses import dataclass
from typing import Iterable, Iterator, Literal, Mapping, Optional, Union

from pydantic import Field, field_validator

from models.input_conf.custom_types import OSType, StrictModel
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


# ─── Walk ─────────────────────────────────────────────────────────────────────


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


def node_dns_labels(node: Node) -> list[str]:
    """The DNS labels a node publishes: its ``dns_name`` entries, or its own name.

    Empty when the node opted out with ``dns: false``. These are bare labels, not
    hostnames — ``settings.dns.local_dns_suffix`` is appended by ``src/dns/find.py``.
    Uniqueness is checked on the labels alone (``YamlRoot``), which is equivalent
    since every record shares the one suffix.
    """
    if not node.dns:
        return []
    return list(node.dns_name) if node.dns_name else [node.name]


# ─── Find ─────────────────────────────────────────────────────────────────────
#
# A *node id* is how a user names one machine: its name or its IP. It is what
# `settings.proxy.deploy.target`, `settings.dns.pihole.target` and
# `labops wake <node>` all take.
#
# Not the vmid, though Proxmox names a guest by it. A vmid is unique only per
# Proxmox node, so it identifies a guest only together with its parent — and being
# an int in a field of strings, it needed a coercion of its own on every config
# field that accepted one. Two ids that always work beat three where one sometimes
# does.


class NodeNotFound(ValueError):
    """No node in the config matches the given name or IP.

    A ValueError like any other config error, so callers that only want a clean
    message need no extra handling. Its own type so a caller can tell "no such
    node" apart from "ambiguous" — the two must never be treated alike, since one
    means the id is wrong and the other that it is not specific enough.
    """


def node_matches(node: Node, node_id: str) -> bool:
    """Whether ``node_id`` — a name or IP — names this node.

    The single answer to that question. The four copies this replaces disagreed:
    hosts matched on their dict key rather than their (possibly overridden) name,
    and only LXCs matched on vmid — the third identifier, since dropped.

    ``node.name`` is the *effective* name — the key, unless the node overrode it.
    A node that set ``name:`` is therefore no longer reachable by its key, which is
    what the field is for: "set it when the key is not the name you want to target
    and publish". One node, one name.
    """
    return node_id in (node.name, str(node.ip))


def _quote(node_id: str, setting: Optional[str]) -> str:
    """The id as an error names it — prefixed by the config key it came from."""
    return f"{setting} '{node_id}'" if setting else f"'{node_id}'"


def find_node(
    hosts: Optional[Mapping[str, Host]],
    node_id: str,
    setting: Optional[str] = None,
) -> NodeRef:
    """The one host, VM or LXC that ``node_id`` names.

    At most one, always: ``YamlRoot.validate_unique_names`` makes names unique
    tree-wide and ``validate_unique_ips`` does the same for addresses, so the first
    match is the only match. That is also why this matches across all three kinds at
    once rather than trying them in an order — the per-kind lookup it replaces went
    LXC, then VM, then Host, and a collision between kinds resolved silently to
    whichever came first.

    ``setting`` names the config key being resolved, when there is one, so a miss
    points at the user's YAML rather than at this function.
    """
    for ref in iter_nodes(hosts):
        if node_matches(ref.node, node_id):
            return ref

    raise NodeNotFound(
        f"{_quote(node_id, setting)} was not found in the configuration "
        "(checked every host, VM and LXC by name and IP)."
    )


# ─── Select ───────────────────────────────────────────────────────────────────

# The node's class in the tree. Deliberately *not* named "type": Host.type /
# VM.type already exists in the config and means the hardware kind
# (bare-metal | proxmox). Two different meanings for one word in one YAML file
# is a support question waiting to happen.
NodeKind = Literal["host", "vm", "lxc"]


class Selector(StrictModel):
    """Which nodes a command acts on. Every field empty means "no constraint".

    AND across fields, OR within a field::

        kind: [lxc], os: [debian]  ->  debian containers
        tags: [prod, edge]         ->  tagged prod OR edge

    A Pydantic model rather than a parsed string because it has two front doors
    that must agree: the ``labops update`` CLI options, and the reusable named sets
    under ``settings.targets``. One model means one matcher, one set of error
    messages, and no grammar to keep in sync.
    """

    kind: list[NodeKind] = Field(
        [],
        description=(
            "Node classes to include: `host`, `vm`, `lxc`. Note this is the "
            "node's place in the tree, not a node's `type` field, which means "
            "bare-metal vs proxmox. A single value may be written unquoted "
            "instead of as a list."
        ),
    )
    os: list[OSType] = Field(
        [],
        description=(
            "Operating systems to include: `debian`, `alpine`, `redhat`, `unmanaged`."
        ),
    )
    tags: list[str] = Field(
        [],
        description=(
            "Match nodes carrying any of these tags. Tags are local to the node "
            "that declares them and are not inherited, so use `under` to sweep a "
            "subtree."
        ),
    )
    under: list[str] = Field(
        [],
        description=(
            "Node names. Matches each named node and everything below it, so "
            "this is how you select a whole Proxmox host with its guests. An "
            "unknown name is an error rather than an empty selection, which "
            "would look like a successful no-op."
        ),
    )
    exclude: list[str] = Field(
        [],
        description=(
            "Node names to exclude. Each named node and everything below it "
            "is removed after the positive filters have run. An unknown name "
            "is an error, same as `under`."
        ),
    )

    @field_validator("kind", "os", "tags", "under", "exclude", mode="before")
    @classmethod
    def _to_list(cls, v: object) -> object:
        # `kind: lxc` is the obvious way to write a single value; accept it,
        # mirroring WebService._normalize_access_to_list.
        return [v] if isinstance(v, str) else v

    @property
    def is_empty(self) -> bool:
        return not (self.kind or self.os or self.tags or self.under or self.exclude)

    def describe(self) -> str:
        """The selector as the flags that would produce it — for error output."""
        parts: list[str] = []
        for flag, values in (
            ("--kind", self.kind),
            ("--os", self.os),
            ("--tag", self.tags),
            ("--under", self.under),
            ("--exclude", self.exclude),
        ):
            parts += [f"{flag} {v}" for v in values]
        return " ".join(parts) if parts else "(everything)"


def node_kind(node: Node) -> NodeKind:
    if isinstance(node, LXC):
        return "lxc"
    if isinstance(node, VM):
        return "vm"
    return "host"


def matches(ref: NodeRef, sel: Selector) -> bool:
    if sel.kind and node_kind(ref.node) not in sel.kind:
        return False
    if sel.os and ref.node.os not in sel.os:
        return False
    if sel.tags and not (set(sel.tags) & set(ref.node.tags)):
        return False
    if sel.under and not (set(sel.under) & set(ref.path)):
        return False
    if sel.exclude and (set(sel.exclude) & set(ref.path)):
        return False
    return True


def unknown_under_names(
    hosts: Optional[Mapping[str, Host]], names: Iterable[str]
) -> list[str]:
    """Which of ``names`` match no node anywhere in the tree.

    Names only, not the full node-id rule: ``under`` selects a subtree by walking
    ``NodeRef.path``, and an IP is not a path segment.
    """
    known: set[str] = {name for ref in iter_nodes(hosts) for name in ref.path}
    return [name for name in names if name not in known]


def select_nodes(hosts: Optional[Mapping[str, Host]], sel: Selector) -> list[NodeRef]:
    """Nodes matching ``sel``, in tree order.

    Raises ``KeyError`` if an ``under`` name matches no node — the common typo,
    which would otherwise silently select nothing and look like "all done".
    """
    missing: list[str] = unknown_under_names(hosts, sel.under)
    missing += unknown_under_names(hosts, sel.exclude)
    if missing:
        raise KeyError(
            f"No host, VM or LXC named {', '.join(repr(m) for m in missing)}."
        )
    return [ref for ref in iter_nodes(hosts) if matches(ref, sel)]
