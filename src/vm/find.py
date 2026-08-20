"""VMs, for the ``labops vm`` listings and updates.

Matching is ``models.nodes.node_matches``, so a VM is findable by its vmid here as
well as from ``labops wake`` — it used to be name-or-IP only, which made
``target: 201`` resolve for a container but not for a virtual machine.
"""

from models.input_conf.vm import VM
from models.input_conf.yaml_root import YamlRoot
from models.nodes import node_matches


def findAll(config: YamlRoot) -> list[VM]:
    """Returns every VM in the Yaml config, at any nesting depth."""
    if config.hosts is None:
        raise KeyError("No hosts are defined in the configuration.")

    return [ref.node for ref in config.iter_nodes() if isinstance(ref.node, VM)]


def find(config: YamlRoot, targets: list[str]) -> list[VM]:
    """Find specific VMs defined in the Yaml config by name or IP."""
    candidates: list[VM] = findAll(config)
    found_vms: list[VM] = []

    for target in targets:
        matches: list[VM] = [vm for vm in candidates if node_matches(vm, target)]
        if not matches:
            raise KeyError(
                f"VM '{target}' was not found in the configuration by name or IP."
            )
        # At most one: names and IPs are both unique across the whole tree.
        found_vms.append(matches[0])

    return found_vms
