"""Top-level hosts, for the ``labops host`` listings and updates.

Matching is ``models.nodes.node_matches`` — the same rule every other lookup uses.
It used to be a local key-or-IP check, which meant a host that overrode its ``name``
was findable by the dict key alone, while ``labops wake`` found it by the name. One
matcher, one answer.
"""

from models.input_conf.host import Host
from models.input_conf.yaml_root import YamlRoot
from models.nodes import node_matches


def findAll(config: YamlRoot) -> list[Host]:
    if config.hosts is None:
        raise KeyError("No hosts are defined in the configuration.")
    return list(config.hosts.values())


def find(config: YamlRoot, targets: list[str]) -> list[Host]:
    """Find specific top-level hosts by name or IP."""
    candidates: list[Host] = findAll(config)
    found_hosts: list[Host] = []

    for target in targets:
        matches: list[Host] = [h for h in candidates if node_matches(h, target)]
        if not matches:
            raise KeyError(
                f"Host '{target}' was not found in the configuration by name or IP."
            )
        # At most one: names and IPs are both unique across the whole tree.
        found_hosts.append(matches[0])

    return found_hosts
