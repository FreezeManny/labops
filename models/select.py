"""Selecting a subset of the config tree.

``models/tree.py`` walks every node; this decides which of them a command acts
on. A ``Selector`` is four optional lists — kind, os, tags, under — combined as
AND across fields and OR within a field, so ``kind: [lxc], os: [debian]`` reads
as "debian containers" and ``tags: [prod, edge]`` as "tagged prod or edge".

It is a Pydantic model rather than a parsed string because it has two front
doors that must agree: the ``labops update`` CLI options, and the reusable named
sets under ``settings.targets``. One model means one matcher, one set of error
messages, and no grammar to keep in sync.

Like ``models/tree.py`` the entry point takes ``hosts`` rather than a
``YamlRoot``: ``settings.py`` imports ``Selector`` for its ``targets`` field, so
depending on the root here would close a cycle. ``YamlRoot.select`` is the front
door.
"""

from typing import Iterable, Literal, Mapping, Optional

from pydantic import Field, field_validator

from models.input_conf.custom_types import OSType, StrictModel
from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.vm import VM
from models.tree import Node, NodeRef, iter_nodes

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
            "Operating systems to include: `debian`, `alpine`, `redhat`, "
            "`unmanaged`."
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

    @field_validator("kind", "os", "tags", "under", mode="before")
    @classmethod
    def _to_list(cls, v: object) -> object:
        # `kind: lxc` is the obvious way to write a single value; accept it,
        # mirroring WebService._normalize_access_to_list.
        return [v] if isinstance(v, str) else v

    @property
    def is_empty(self) -> bool:
        return not (self.kind or self.os or self.tags or self.under)

    def describe(self) -> str:
        """The selector as the flags that would produce it — for error output."""
        parts: list[str] = []
        for flag, values in (
            ("--kind", self.kind),
            ("--os", self.os),
            ("--tag", self.tags),
            ("--under", self.under),
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
    return True


def unknown_under_names(
    hosts: Optional[Mapping[str, Host]], names: Iterable[str]
) -> list[str]:
    """Which of ``names`` match no node anywhere in the tree."""
    known: set[str] = {name for ref in iter_nodes(hosts) for name in ref.path}
    return [name for name in names if name not in known]


def select_nodes(hosts: Optional[Mapping[str, Host]], sel: Selector) -> list[NodeRef]:
    """Nodes matching ``sel``, in tree order.

    Raises ``KeyError`` if an ``under`` name matches no node — the common typo,
    which would otherwise silently select nothing and look like "all done".
    """
    missing: list[str] = unknown_under_names(hosts, sel.under)
    if missing:
        raise KeyError(
            f"No host, VM or LXC named {', '.join(repr(m) for m in missing)}."
        )
    return [ref for ref in iter_nodes(hosts) if matches(ref, sel)]
