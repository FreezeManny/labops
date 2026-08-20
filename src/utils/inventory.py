"""How labops reaches a node: the connection half of every generated inventory.

Every command that runs a playbook has to turn a config node plus its ``Creds``
into inventory host_vars. ``creds_for`` answers the first half — *which* ``Creds``
reach a node — and is the only place the "the node's own, else the default" rule
is written down. There are two ways labops reaches a node, and they differ in
more than the connection plugin:

* **direct SSH** (bare-metal host, VM, Docker target) — needs the sudo password
  for ``become``;
* **pct** (LXC) — Ansible SSHes to the container's *Proxmox node* and uses
  ``pct exec``/``pct push`` from there, so the container needs no sshd, and no
  become password either because ``pct`` already runs as root.

Callers add their own keys on top (``compose_src``, group placement, aliases);
what lives here is the connection + auth part, so the plugin name and the
credential mapping each exist once.

``connection_for`` sits on top: it is the whole answer for a command that acts on
"the node named X" rather than on a selection —
``settings.proxy.deploy.target`` (where Caddy runs), ``settings.dns.pihole.target``
(where Pi-hole runs), ``wake --via``. It does no searching of its own; finding the
node is models/nodes.py's job, and all that is left here is choosing between the
two functions above.

That is also why this is one module rather than two. It used to be split, because
the lookup needed the per-kind finders and ``src.host``'s package init imports
``inventory`` — a cycle. With the search in ``models``, which imports no ``src``,
the cycle cannot form.
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from models.input_conf.creds import Creds
from models.input_conf.lxc import LXC
from models.nodes import Node, NodeRef

if TYPE_CHECKING:  # a runtime import of the root model would close another cycle
    from models.input_conf.yaml_root import YamlRoot

PCT_CONNECTION = "community.proxmox.proxmox_pct_remote"


def ssh_host_vars(creds: Creds, ip: Optional[str] = None) -> dict:
    """Host_vars for a node reached over plain SSH.

    ``ip`` sets ``ansible_host``; omit it when the inventory key is already the
    address, as in the host/VM update inventories which are keyed by IP.
    """
    host_vars: dict = {}
    if ip is not None:
        host_vars["ansible_host"] = ip
    host_vars["ansible_user"] = creds.username
    if creds.password:
        host_vars["ansible_password"] = creds.password
        host_vars["ansible_become_password"] = creds.password
    if creds.ssh_key_path:
        host_vars["ansible_ssh_private_key_file"] = str(creds.ssh_key_path)
    return host_vars


def pct_host_vars(node_ip: str, vmid: int, creds: Creds) -> dict:
    """Host_vars for one LXC, reached via its Proxmox node.

    ``creds`` are the *node's* credentials (that is what Ansible authenticates
    against) and ``node_ip`` is the node's address, not the container's. No
    become password: inside ``pct exec`` the session is already root.
    """
    host_vars: dict = {
        "ansible_connection": PCT_CONNECTION,
        "ansible_host": node_ip,
        "ansible_user": creds.username,
        "proxmox_vmid": vmid,
    }
    if creds.ssh_key_path:
        host_vars["ansible_ssh_private_key_file"] = str(creds.ssh_key_path)
    if creds.password:
        host_vars["ansible_password"] = creds.password
    return host_vars


@dataclass(frozen=True)
class NodeConnection:
    """A config node together with the inventory entry that reaches it.

    Both halves are needed: ``host_vars`` to run anything, and ``node`` to ask
    questions about it first — ``dns upgrade`` refuses to run on an ``unmanaged``
    node, which it can only know by looking.
    """

    node: Node
    host_vars: dict


def connection_for(
    config: "YamlRoot", node_id: str, setting: Optional[str] = None
) -> NodeConnection:
    """The node ``node_id`` names, with the host_vars that reach it.

    An LXC is reached via the pct connection through its parent — no sshd needed in
    the container — while a VM or bare-metal host is reached over direct SSH. Which
    node it is has already been decided by ``find_node``; the only question here is
    which of the two shapes above it takes.

    ``setting`` names the config key being resolved, so a miss points at the user's
    YAML rather than at this function.
    """
    ref: NodeRef = config.find_node(node_id, setting)
    default_creds: Optional[Creds] = config.settings.default_creds

    if isinstance(ref.node, LXC):
        # The *parent's* credentials and address: that is what Ansible connects to
        # before running `pct`. An LXC always has one — only a host sits at the root.
        assert ref.parent is not None
        creds: Creds = creds_for(ref.parent, default_creds, setting)
        return NodeConnection(
            node=ref.node,
            host_vars=pct_host_vars(str(ref.parent.ip), ref.node.vmid, creds),
        )

    creds = creds_for(ref.node, default_creds, setting)
    return NodeConnection(
        node=ref.node, host_vars=ssh_host_vars(creds, str(ref.node.ip))
    )


def creds_for(
    node: Node, default_creds: Optional[Creds], setting: Optional[str] = None
) -> Creds:
    """The credentials that reach ``node``: its own, or ``settings.default_creds``.

    The one statement of that fallback. It used to be written out at each of the
    seven places that needed it, and once `default_creds` became optional every
    one of them would have grown its own None check as well.

    Raising rather than returning ``None`` is what keeps those callers to a single
    line. It is close to unreachable for a node reached by ``update`` or ``setup``:
    those act only on managed nodes, and `YamlRoot.validate_creds_available` refuses
    to load a config where one of those has no credentials, so the failure lands at
    `labops validate` rather than half-way through a sweep. What it does catch is a
    node named by hand in a setting — `settings.dns.pihole.target` and friends —
    which may be `os: unmanaged`, and so is exempt from that check.

    ``setting`` names the config key that led here, when one did.
    """
    creds: Optional[Creds] = node.creds or default_creds
    if creds is not None:
        return creds
    where: str = f"{setting}: " if setting else ""
    raise ValueError(
        f"{where}'{node.name}' has no credentials — it carries no 'creds' of its "
        "own and settings.default_creds is unset. Set one of the two; labops has "
        "to log in to run anything on it."
    )


def host_vars_for(
    config: "YamlRoot", node_id: str, setting: Optional[str] = None
) -> dict:
    """Just the inventory half of ``connection_for``, for callers that only run."""
    return connection_for(config, node_id, setting).host_vars
