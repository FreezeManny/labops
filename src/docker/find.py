from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Optional, Union

from models.input_conf.yaml_root import YamlRoot
from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.vm import VM
from models.input_conf.docker import StackEntry

from models.docker.stack_result import StackResult


# ─── Recursive walker ────────────────────────────────────────────────────────

def _walk(node: Union[Host, VM, LXC], path: list[str], results: list[StackResult]) -> None:
    """Recursively collect StackResults from any node that can carry docker/vm/lxc."""
    if node.docker:
        for stack in node.docker.stacks.values():
            results.append(StackResult(
                path=list(path),
                target_ip=node.ip,
                docker_root=node.docker.root_path,
                stack=stack,
                creds=node.creds,
            ))

    # VMs can nest further VMs or LXCs
    for name, child in (getattr(node, "vm", None) or {}).items():
        _walk(child, path + [name], results)

    # LXCs are leaves (no further nesting in the model)
    for name, child in (getattr(node, "lxc", None) or {}).items():
        _walk(child, path + [name], results)


# ─── Public API ───────────────────────────────────────────────────────────────

def findAll(config: YamlRoot) -> list[StackResult]:
    """Return every stack at any nesting depth across all hosts."""
    results: list[StackResult] = []
    if config.hosts is None:
        return results

    for host_name, host in config.hosts.items():
        _walk(host, [host_name], results)

    return results


def find(
    config:     YamlRoot,
    stack_name: Optional[str] = None,
    node_name:  Optional[str] = None,
) -> list[StackResult]:
    """
    Find stacks filtered by path segment and/or stack name.

    - node_name:  matches any segment in the path (host, VM, or LXC name).
    - stack_name: narrows to a specific stack; raises if still ambiguous.
    """
    results: list[StackResult] = findAll(config)

    if node_name:
        matched: list[StackResult] = [r for r in results if node_name in r.path]
        if not matched:
            raise KeyError(
                f"'{node_name}' did not match any host, VM, or LXC with Docker stacks."
            )
        results = matched

    if stack_name:
        matched: list[StackResult] = [r for r in results if r.stack.name == stack_name]
        if not matched:
            raise KeyError(f"Stack '{stack_name}' was not found.")
        if len(matched) > 1 and not node_name:
            locations = ", ".join("/".join(r.path) for r in matched)
            raise KeyError(
                f"Stack '{stack_name}' exists in multiple locations: {locations}. "
                "Use --node to disambiguate."
            )
        results = matched

    return results
