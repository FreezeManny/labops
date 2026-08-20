"""LXCs with the node they are reached through, for the ``labops lxc`` commands.

Matching is ``models.nodes.node_matches``. What is local here is the *pair*: an LXC
on its own does not know how it is reached, and ``pct`` runs on its parent.
"""

from models.input_conf.lxc import LXC
from models.input_conf.yaml_root import YamlRoot
from models.nodes import Parent, node_matches

# The node an LXC is reached *through*, i.e. the one labops SSHes to in order to
# run `pct`. For a top-level container that is the Proxmox Host; for one nested
# inside a VM it is that VM. Both carry the ip/creds/name a pct inventory needs.
LXCParent = Parent

# (parent, container) — the pair every caller needs, since an LXC on its own does
# not know how it is reached.
LXCPair = tuple[LXCParent, LXC]


def findAll(config: YamlRoot) -> list[LXCPair]:
    """Returns every LXC in the Yaml config, at any depth, with its parent node."""
    return [
        (ref.parent, ref.node)
        for ref in config.iter_nodes()
        # An LXC always has a parent — only a host sits at the root — but the
        # check narrows the Optional for the type checker as well.
        if isinstance(ref.node, LXC) and ref.parent is not None
    ]


def find(config: YamlRoot, targets: list[str]) -> list[LXCPair]:
    """Find specific LXCs defined in the Yaml config by name or IP."""
    candidates: list[LXCPair] = findAll(config)
    results: list[LXCPair] = []

    for target in targets:
        matches: list[LXCPair] = [p for p in candidates if node_matches(p[1], target)]
        if not matches:
            raise KeyError(f"LXC '{target}' was not found in the configuration.")
        # At most one: names and IPs are both unique across the whole tree.
        results.append(matches[0])
    return results
