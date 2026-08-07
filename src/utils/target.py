"""Resolving a named config node to the inventory that reaches it.

Some commands act on "the node named X in the config" rather than on a selection:
``settings.proxy.deploy.target`` (where Caddy runs) and ``settings.dns.target``
(where Pi-hole runs). Both need the same lookup — name, IP or vmid to a single
host's ``host_vars`` — so it lives here once.

Separate from ``src/utils/inventory.py`` on purpose: this needs the per-kind
finders, and ``src.host``'s package init imports ``inventory``, so putting it
there would close an import cycle (inventory -> host.find -> host -> host.update
-> inventory). ``inventory`` stays dependency-free; the finders compose on top.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from models.input_conf.creds import Creds
from models.tree import Node
from src.host.find import find as find_hosts
from src.lxc.find import find as find_lxcs
from src.utils.inventory import pct_host_vars, ssh_host_vars
from src.vm.find import find as find_vms

if TYPE_CHECKING:  # a runtime import of the root model would close another cycle
    from models.input_conf.yaml_root import YamlRoot


class TargetNotFound(ValueError):
    """No node in the config matches the given name, IP or vmid.

    A ValueError like any other config error, so callers that only want a clean
    message need no extra handling. Its own type so a caller that has somewhere
    *else* to look — ``settings.dns.pihole_location`` also accepts a docker stack
    — can tell "not a node" apart from "ambiguous", which must not fall through.
    """


@dataclass(frozen=True)
class ResolvedTarget:
    """A named config node together with the inventory entry that reaches it.

    Both halves are needed: ``host_vars`` to run anything, and ``node`` to ask
    questions about it first — ``dns upgrade`` refuses to run on an ``unmanaged``
    node, which it can only know by looking.
    """

    node: Node
    host_vars: dict


def resolve_target(config: "YamlRoot", target: str, setting: str) -> ResolvedTarget:
    """Resolve ``target`` (a name, IP or vmid) to the node and how to reach it.

    An LXC is reached via the pct connection through its Proxmox node — no sshd
    needed in the container — while a VM or bare-metal host is reached over direct
    SSH. Tried most-specific first, since an LXC also matches by vmid and the
    namespaces would otherwise collide. An ambiguous target raises out of the
    finder rather than being resolved here.

    ``setting`` names the config key being resolved, so a miss points at the user's
    YAML rather than at this function.
    """
    default_creds: Creds = config.settings.default_creds

    # LXC → proxmox_pct_remote via the parent node.
    try:
        pairs = find_lxcs(config, [target])
    except KeyError:
        pairs = []
    if pairs:
        parent, lxc_obj = pairs[0]
        creds: Creds = parent.creds or default_creds
        return ResolvedTarget(
            node=lxc_obj,
            host_vars=pct_host_vars(str(parent.ip), lxc_obj.vmid, creds),
        )

    # VM → direct SSH.
    try:
        vms = find_vms(config, [target])
    except KeyError:
        vms = []
    if vms:
        vm = vms[0]
        creds = vm.creds or default_creds
        return ResolvedTarget(node=vm, host_vars=ssh_host_vars(creds, str(vm.ip)))

    # Bare-metal / Proxmox host → direct SSH.
    try:
        hosts = find_hosts(config, [target])
    except KeyError:
        hosts = []
    if hosts:
        host = hosts[0]
        creds = host.creds or default_creds
        return ResolvedTarget(node=host, host_vars=ssh_host_vars(creds, str(host.ip)))

    raise TargetNotFound(
        f"{setting} '{target}' matches no host, VM or LXC in the config "
        "(checked by name and IP, plus vmid for LXCs)."
    )


def resolve_node_host_vars(config: "YamlRoot", target: str, setting: str) -> dict:
    """Just the inventory half of ``resolve_target``, for callers that only run."""
    return resolve_target(config, target, setting).host_vars
