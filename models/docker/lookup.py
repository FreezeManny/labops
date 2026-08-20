"""Finding a docker stack by name, and saying why a name did not resolve.

Lives in ``models`` rather than beside src/docker/find.py because the config
validators need it: ``settings.dns.pihole.docker_stack`` is checked at load, and a
validator cannot import ``src`` — src/docker/find.py takes a ``YamlRoot``, which is
the module the validators are in.

So the split is by what the answer has to carry. ``findAll`` builds a
``StackResult`` — creds, docker root, the target IP — because the commands run
against the stack. Nothing here needs any of that: a validator only asks whether
the name resolves to exactly one stack, which is a walk over the same tree.

The messages are shared rather than the walk, which is what keeps load-time and
run-time agreeing about a name. Both callers ask the same two questions in the same
order — no match, or several — so a name that loads is a name that resolves.
"""

from typing import Mapping, Optional

from models.input_conf.host import Host
from models.nodes import NodeRef, iter_nodes


def stack_paths(hosts: Optional[Mapping[str, Host]], name: str) -> list[list[str]]:
    """The path of every stack answering to ``name``, at any depth, in tree order.

    A list because stack names need not be unique across the config — the same
    compose stack on two nodes is a normal thing to declare, and only a caller that
    needs *one* of them treats that as an error.

    Matches on the effective name (the key, unless the stack overrides it), which is
    the name the user passes to the commands.
    """
    found: list[list[str]] = []

    for ref in iter_nodes(hosts):
        node_ref: NodeRef = ref
        docker = node_ref.node.docker
        if not docker:
            continue
        for stack in docker.stacks.values():
            if stack.name == name:
                found.append(node_ref.path)

    return found


def no_stack_message(setting: str, name: str) -> str:
    """``setting`` names a stack that does not exist — a typo, or the wrong key."""
    return (
        f"{setting} '{name}' matches no docker stack in the config. Name a stack "
        "declared under some node's `docker.stacks`, or use `target:` if "
        "Pi-hole is installed on the machine rather than containerised."
    )


def ambiguous_stack_message(setting: str, name: str, paths: list[list[str]]) -> str:
    """``setting`` names a stack that exists more than once.

    A separate message from the miss above: that one means the name is wrong, this
    one that it is not specific enough, and the two have different fixes.
    """
    locations: str = ", ".join(" → ".join(path) for path in paths)
    return (
        f"{setting} '{name}' exists in multiple locations: {locations}. Rename "
        "one of them, or point at the node running it with `target:` instead."
    )
