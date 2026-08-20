from typing import Iterable, Optional

from models.input_conf.yaml_root import YamlRoot
from models.input_conf.creds import Creds
from models.nodes import NodeRef

from models.docker.stack_result import StackResult


# ─── Public API ───────────────────────────────────────────────────────────────


def stacks_for(refs: Iterable[NodeRef], default_creds: Creds) -> list[StackResult]:
    """The stacks running on the given nodes.

    A stack is not independently addressable — it has no os, no kind, and its
    path is its node's path — so selection picks nodes and the stacks come
    along. This is the whole node-to-stack bridge.
    """
    results: list[StackResult] = []

    for ref in refs:
        docker = ref.node.docker
        if not docker:
            continue
        for stack in docker.stacks.values():
            results.append(
                StackResult(
                    path=ref.path,
                    target_ip=ref.node.ip,
                    docker_root=docker.root_path,
                    stack=stack,
                    creds=(
                        ref.node.creds if ref.node.creds is not None else default_creds
                    ),
                )
            )

    return results


def findAll(config: YamlRoot) -> list[StackResult]:
    """Return every stack at any nesting depth across all hosts."""
    return stacks_for(config.iter_nodes(), config.settings.default_creds)


def find(
    config: YamlRoot,
    stack_name: Optional[str] = None,
    node_name: Optional[str] = None,
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
            locations: str = ", ".join("/".join(r.path) for r in matched)
            raise KeyError(
                f"Stack '{stack_name}' exists in multiple locations: {locations}. "
                "Use --node to disambiguate."
            )
        results = matched

    return results
