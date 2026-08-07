"""Working out where Pi-hole is, from ``settings.dns.pihole_location``.

That one field carries three shapes, because the two DNS commands need different
things from it:

* a **config node** (name, IP or vmid) — the full answer. Records go to the node's
  address, and ``dns upgrade`` has a node to SSH into.
* a **docker stack** — Pi-hole in a container. Records go to the hosting node's
  address, exactly as a proxied stack's services do (see src/proxy/find.py), but
  ``dns upgrade`` must refuse: `pihole -up` upgrades an installation, and a
  container is upgraded by pulling a new image.
* a **bare IP** matching nothing in the config — a Pi-hole labops does not
  otherwise manage. Records work; there is nothing to SSH into.

Resolving all three in one place means ``dns sync`` and ``dns upgrade`` cannot
disagree about what the field meant, and it is what makes the Docker refusal
reliable: the user says Pi-hole is a stack rather than labops guessing from stack
names.

Takes ``dns`` as an argument rather than reaching for ``require_dns``: that lives in
sync.py, which imports this module.
"""

from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Optional

from models.docker.stack_result import StackResult
from models.input_conf.dns import Dns
from models.input_conf.yaml_root import YamlRoot
from src.docker.find import find as find_stacks
from src.utils.target import ResolvedTarget, TargetNotFound, resolve_target

SETTING = "settings.dns.pihole_location"


@dataclass(frozen=True)
class PiholeLocation:
    """Where Pi-hole is. Exactly one of ``node`` / ``stack`` is set, or neither."""

    # The address to call the API on — always known, whichever shape matched.
    address: str
    # What the location named, as written by the user.
    target: str
    node: Optional[ResolvedTarget] = None
    stack: Optional[StackResult] = None

    @property
    def is_stack(self) -> bool:
        return self.stack is not None

    @property
    def where(self) -> str:
        """Human-readable location, for messages."""
        if self.stack is not None:
            return " → ".join(self.stack.path)
        return self.target


def _as_stack(config: YamlRoot, target: str) -> Optional[StackResult]:
    """The docker stack named ``target``, if there is one.

    A stack name that exists on several nodes raises out of the finder rather than
    being picked arbitrarily — same treatment as an ambiguous node.
    """
    try:
        matches: list[StackResult] = find_stacks(config, stack_name=target)
    except KeyError:
        return None
    return matches[0] if matches else None


def resolve_location(config: YamlRoot, dns: Dns) -> PiholeLocation:
    """Resolve ``settings.dns.pihole_location`` to a node, a stack, or a bare IP.

    Nodes are tried first: they are the common case, and a node is the only shape
    that supports every command. A name that is *both* a node and a stack is an
    error rather than a silent preference — the two would send `dns upgrade`
    somewhere different.

    ``pihole_location`` is optional, so this is also where "you have not said where
    Pi-hole is" is reported. It is deliberately not a config-validation error:
    deriving records is useful on its own, and ``dns list`` never comes through
    here.
    """
    if dns.pihole_location is None:
        raise ValueError(
            f"{SETTING} is not set, so labops does not know which Pi-hole to talk "
            "to. Set it to the node running Pi-hole (by name, IP or vmid), the "
            "docker stack running it, or its address. `dns list` works without it."
        )
    target: str = dns.pihole_location

    node: Optional[ResolvedTarget]
    try:
        node = resolve_target(config, target, SETTING)
    except TargetNotFound:
        node = None  # may still be a stack, or a bare address

    stack: Optional[StackResult] = _as_stack(config, target)

    if node is not None and stack is not None:
        raise ValueError(
            f"{SETTING} '{target}' is ambiguous: it names both a host/VM/LXC and a "
            f"docker stack on {' → '.join(stack.path)}. Rename one of them."
        )
    if node is not None:
        return PiholeLocation(address=str(node.node.ip), target=target, node=node)
    if stack is not None:
        # A stack's services are published on its host node's address, which is why
        # the stack name is not part of the address.
        return PiholeLocation(
            address=str(stack.target_ip), target=target, stack=stack
        )

    try:
        return PiholeLocation(address=str(IPv4Address(target)), target=target)
    except ValueError:
        raise ValueError(
            f"{SETTING} '{target}' matches no host, VM, LXC or docker stack in the "
            "config, and is not an IP address. Name the node running Pi-hole (by "
            "name, IP or vmid), the docker stack running it, or its address."
        ) from None
