"""Working out where a service is, from a ``target`` / ``docker_stack`` block.

Nothing here is specific to one DNS server: it is the lookup behind
``settings.dns.pihole``, and any other backend's block declares its location the
same two ways. Two keys, one of which is set, because the commands need different
things from the answer:

* ``target`` — the machine the service is installed on, always a node in this
  config (by name or IP). Records go to that node's address, and an upgrade has
  something to run a command on. A machine labops does not otherwise manage is
  declared like any other node with ``os: unmanaged``, rather than named by a bare
  address: records work either way, and stating it keeps the node inside the
  uniqueness and DNS-label checks instead of outside them.
* ``docker_stack`` — the service in a container. Records go to the hosting node's
  address, exactly as a proxied stack's services do (see src/proxy/find.py), but an
  upgrade must refuse: a container is upgraded by pulling a new image.

Which key is set is the user's statement of *what kind of thing* it is, and that is
the one thing an address cannot tell you — a container and an installation are
reached at the same IP. So nothing here infers it: a name that is both a node and a
stack is not a problem, and the container refusal is reliable rather than a guess.
Resolving both in one place is what keeps the record commands and the upgrade
command from disagreeing about what the block meant.
"""

from dataclasses import dataclass
from typing import ClassVar, Optional, Union

from models.docker.lookup import ambiguous_stack_message, no_stack_message
from models.docker.stack_result import StackResult
from models.input_conf.yaml_root import YamlRoot
from models.nodes import NodeNotFound
from src.docker.find import findAll as find_all_stacks
from src.utils.inventory import NodeConnection, connection_for


@dataclass(frozen=True)
class _Location:
    """What every location knows, whichever key the user set."""

    # The address to talk to.
    address: str
    # What the location named, as written by the user.
    target: str
    # The config key it came from, for messages about the location — the caller's
    # block prefix plus the key that was set, e.g. "settings.dns.pihole.target".
    setting: str


@dataclass(frozen=True)
class NodeLocation(_Location):
    """``target:`` — the service is installed on a node in this config."""

    node: NodeConnection

    is_stack: ClassVar[bool] = False

    @property
    def where(self) -> str:
        return self.target


@dataclass(frozen=True)
class StackLocation(_Location):
    """``docker_stack:`` — the service runs in a container on a node."""

    stack: StackResult

    is_stack: ClassVar[bool] = True

    @property
    def where(self) -> str:
        return " → ".join(self.stack.path)


# Two cases, not one shape with two optional halves: which key was set decides
# both the address and what an upgrade is allowed to do, so it is the type rather
# than a flag to test. A caller that has ruled out a stack then *has* a node,
# without an assertion standing in for what the type should say.
ServiceLocation = Union[NodeLocation, StackLocation]


def _resolve_stack(config: YamlRoot, name: str, setting: str) -> StackResult:
    """The one docker stack called ``name``, or a ValueError saying why there isn't.

    Not-found and found-on-several-nodes are separate messages: one means the name
    is wrong, the other that it is not specific enough, and the fixes differ. The
    finder collapses both into a ``KeyError``, so the filtering happens here.

    The messages are the ones the config validator raises at load
    (models/docker/lookup.py), so reaching either of them here means the block was
    built after validation rather than read from a loaded config.
    """
    matches: list[StackResult] = [
        found for found in find_all_stacks(config) if found.stack.name == name
    ]
    if not matches:
        raise ValueError(no_stack_message(setting, name))
    if len(matches) > 1:
        raise ValueError(
            ambiguous_stack_message(setting, name, [found.path for found in matches])
        )
    return matches[0]


def _resolve_machine(config: YamlRoot, target: str, setting: str) -> NodeLocation:
    """The node in this config that ``target`` names.

    One outcome, so a miss is always a miss: an off-config address used to resolve
    here as long as it parsed as an IPv4, which meant a fat-fingered address was
    indistinguishable from a deliberate one. The route for a machine labops does not
    manage is ``os: unmanaged``, so the miss is re-raised carrying it — this is the
    error someone upgrading from a bare address lands on.
    """
    try:
        resolved: NodeConnection = connection_for(config, target, setting)
    except NodeNotFound as miss:
        raise NodeNotFound(
            f"{miss} Declare the machine under `hosts:` — with `os: unmanaged` if "
            "labops does not otherwise manage it — and name it here."
        ) from None

    return NodeLocation(
        address=str(resolved.node.ip), target=target, setting=setting, node=resolved
    )


def resolve_service_location(
    config: YamlRoot,
    *,
    setting: str,
    target: Optional[str] = None,
    docker_stack: Optional[str] = None,
) -> ServiceLocation:
    """Resolve whichever of ``target`` / ``docker_stack`` the user set.

    ``setting`` is the block's config path (e.g. ``settings.dns.pihole``); the
    resolved location's own ``setting`` names the key within it, so a message quotes
    what the user actually wrote.

    Dispatches on which key is set, so a miss is a hard error rather than a
    fallthrough to the other shape — naming a stack that does not exist is a typo,
    not an invitation to try the nodes. The caller's model is what guarantees
    exactly one is set; a block with neither is a bug there, not a user error.
    """
    if target is not None:
        return _resolve_machine(config, target, f"{setting}.target")

    if docker_stack is not None:
        key: str = f"{setting}.docker_stack"
        found: StackResult = _resolve_stack(config, docker_stack, key)
        # A stack's services are published on its host node's address, which is why
        # the stack name is not part of the address.
        return StackLocation(
            address=str(found.target_ip),
            target=docker_stack,
            setting=key,
            stack=found,
        )

    raise ValueError(  # the block's own validator is what normally prevents this
        f"{setting} names no location; set exactly one of target: or docker_stack:."
    )
