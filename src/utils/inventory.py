"""Building blocks for the dynamic Ansible inventories labops generates.

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
"""

from typing import Optional

from models.input_conf.creds import Creds

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
