"""How labops reaches a node: the connection half of every generated inventory.

Every command that runs a playbook has to turn a config node plus its ``Creds``
into inventory host_vars. There are two ways labops reaches a node, and they
differ in more than the connection plugin:

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
    if creds.passwd:
        host_vars["ansible_password"] = creds.passwd
        host_vars["ansible_become_password"] = creds.passwd
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
    if creds.passwd:
        host_vars["ansible_password"] = creds.passwd
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
    default_creds: Creds = config.settings.default_creds

    if isinstance(ref.node, LXC):
        # The *parent's* credentials and address: that is what Ansible connects to
        # before running `pct`. An LXC always has one — only a host sits at the root.
        assert ref.parent is not None
        creds: Creds = ref.parent.creds or default_creds
        return NodeConnection(
            node=ref.node,
            host_vars=pct_host_vars(str(ref.parent.ip), ref.node.vmid, creds),
        )

    creds = ref.node.creds or default_creds
    return NodeConnection(
        node=ref.node, host_vars=ssh_host_vars(creds, str(ref.node.ip))
    )


def host_vars_for(
    config: "YamlRoot", node_id: str, setting: Optional[str] = None
) -> dict:
    """Just the inventory half of ``connection_for``, for callers that only run."""
    return connection_for(config, node_id, setting).host_vars
