"""Which node ``labops wake`` should act on.

``wake`` does not know the node's kind in advance — that is exactly what it has to
work out, since a bare-metal host is woken with a magic packet and a Proxmox guest
by starting it on its parent node. So it needs the match across all three kinds at
once, which is ``models.nodes.find_node``, and this is the thin binding to it.

It returns a ``NodeRef`` rather than ``src/utils/inventory.py``'s ``NodeConnection``
because the guest path needs the **parent**: ``qm start`` / ``pct start`` runs on
the Proxmox node, and only the tree walk knows which node that is.
``connection_for`` is still what ``--via`` uses, where inventory host_vars is
precisely the thing wanted.
"""

from typing import TYPE_CHECKING

from models.nodes import NodeRef, find_node

if TYPE_CHECKING:  # a runtime import of the root model would close a cycle
    from models.input_conf.yaml_root import YamlRoot


def resolve_wake_target(config: "YamlRoot", target: str) -> NodeRef:
    """The host, VM or LXC named by ``target`` (name or IP)."""
    return find_node(config.hosts, target)


def wakeable(config: "YamlRoot") -> list[NodeRef]:
    """Every node carrying a ``mac``, in tree order — what ``wake --list`` shows."""
    return [ref for ref in config.iter_nodes() if ref.node.mac]
