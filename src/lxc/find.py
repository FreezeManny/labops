from models.input_conf.yaml_root import YamlRoot
from models.input_conf.lxc import LXC
from models.tree import Parent

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


def _matches(lxc_obj: LXC, target: str) -> bool:
    return target in (lxc_obj.name, str(lxc_obj.ip), str(lxc_obj.vmid))


def find(config: YamlRoot, targets: list[str]) -> list[LXCPair]:
    """Find specific LXCs defined in the Yaml config by Name, IP, or VMID."""
    candidates: list[LXCPair] = findAll(config)
    results: list[LXCPair] = []

    for target in targets:
        matches: list[LXCPair] = [p for p in candidates if _matches(p[1], target)]
        if not matches:
            raise KeyError(f"LXC '{target}' was not found in the configuration.")
        if len(matches) > 1:
            # vmids are only unique per Proxmox node (Host.check_duplicate_vmid),
            # so the same vmid on two nodes is a legal config but an ambiguous
            # target — silently taking the first would act on the wrong container.
            where: str = ", ".join(
                f"'{lxc_obj.name}' (vmid {lxc_obj.vmid}) on '{parent.name}'"
                for parent, lxc_obj in matches
            )
            raise ValueError(
                f"LXC '{target}' is ambiguous — it matches {len(matches)} "
                f"containers: {where}. Target it by name or IP instead."
            )
        results.append(matches[0])
    return results
