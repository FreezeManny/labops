"""Resolving the node ``labops wake`` should act on.

The per-kind finders (``src/host/find.py`` and friends) each answer for one kind,
but ``wake`` does not know the kind in advance — that is exactly what it has to
work out, since a bare-metal host is woken with a magic packet and a Proxmox guest
by starting it on its parent node. So this matches across all three kinds at once.

It returns a ``NodeRef`` rather than ``src/utils/target.py``'s ``ResolvedTarget``
because the guest path needs the **parent**: ``qm start`` / ``pct start`` runs on
the Proxmox node, and only the tree walk knows which node that is.
``resolve_target`` is still what ``--via`` uses, where inventory host_vars is
precisely the thing wanted.

Error convention follows ``src/lxc/find.py``: KeyError for "no match", ValueError
for "matches more than one" — ``src/cli/wake.py`` renders both as one line.
"""

from typing import TYPE_CHECKING

from models.input_conf.host import Host
from models.tree import Node, NodeRef

if TYPE_CHECKING:  # a runtime import of the root model would close a cycle
    from models.input_conf.yaml_root import YamlRoot


def _matches(node: Node, target: str) -> bool:
    """By name or IP, plus vmid for the guests that have one."""
    if target in (node.name, str(node.ip)):
        return True
    # Host has no vmid; VM and LXC do, and it is how Proxmox itself names a guest.
    return not isinstance(node, Host) and target == str(node.vmid)


def resolve_wake_target(config: "YamlRoot", target: str) -> NodeRef:
    """The host, VM or LXC named by ``target`` (name, IP or vmid)."""
    matches: list[NodeRef] = [
        ref for ref in config.iter_nodes() if _matches(ref.node, target)
    ]

    if not matches:
        raise KeyError(
            f"'{target}' was not found in the configuration (checked every host, "
            "VM and LXC by name and IP, plus vmid for guests)."
        )
    if len(matches) > 1:
        # vmids are only unique per Proxmox node and names only per parent, so a
        # collision is a legal config but an ambiguous target — and waking the
        # wrong machine is not something to guess at.
        where: str = ", ".join(f"'{' → '.join(ref.path)}'" for ref in matches)
        raise ValueError(
            f"'{target}' is ambiguous — it matches {len(matches)} nodes: {where}. "
            "Target it by IP instead."
        )
    return matches[0]


def wakeable(config: "YamlRoot") -> list[NodeRef]:
    """Every node carrying a ``mac``, in tree order — what ``wake --list`` shows."""
    return [ref for ref in config.iter_nodes() if ref.node.mac]
