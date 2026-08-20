"""The two Ansible-driven wake paths.

``packet.py`` covers the case where labops itself can reach the target's segment.
The two here cover the cases where something else has to act on its behalf:

* **``send_via``** — the magic packet is broadcast from another node in the config.
  A limited broadcast is not forwarded between subnets, so a laptop on the VPN
  cannot wake a NAS on the lab LAN; a node that *is* on that LAN can.
* **``start_guest``** — a Proxmox VM or LXC. A magic packet cannot start one:
  nothing in a stopped guest is listening, and Proxmox does not watch for WoL on a
  guest's behalf. The equivalent is ``qm start`` / ``pct start``, run over SSH on
  the parent node — the same way ``lxc update`` reaches a container.

Both go through ``run_playbook``, so ``--dry-run`` (ansible ``--check``) and
``--verbose`` behave exactly as they do everywhere else.
"""

from typing import TYPE_CHECKING, Optional

from ansible_runner import Runner

from models.input_conf.creds import Creds
from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.nodes import Node, NodeRef, Parent
from src.utils.ansible_runner import run_playbook
from src.utils.inventory import creds_for, ssh_host_vars
from src.utils.inventory import NodeConnection, connection_for
from src.wake.packet import DEFAULT_BROADCAST, DEFAULT_PORT

if TYPE_CHECKING:  # a runtime import of the root model would close a cycle
    from models.input_conf.yaml_root import YamlRoot

VIA_SETTING = "--via"

# Inventory aliases only — every run here targets exactly one host.
_RELAY_ALIAS = "wake_relay"
_PARENT_ALIAS = "wake_parent"


def guest_cli(node: NodeRef) -> str:
    """The Proxmox command that starts this guest: ``pct`` for an LXC, else ``qm``."""
    return "pct" if isinstance(node.node, LXC) else "qm"


def send_via(
    config: "YamlRoot",
    mac: str,
    via: str,
    broadcast: str = DEFAULT_BROADCAST,
    port: int = DEFAULT_PORT,
    dry_run: bool = False,
    verbose: bool = False,
) -> Runner:
    """Broadcast the magic packet from the config node named by ``via``."""
    relay: NodeConnection = connection_for(config, via, VIA_SETTING)
    inventory: dict = {
        "all": {"hosts": {f"{_RELAY_ALIAS}_{relay.node.name}": relay.host_vars}}
    }
    return run_playbook(
        playbook="wake/packet.yml",
        inventory=inventory,
        extravars={
            "wake_mac": mac,
            "wake_broadcast": broadcast,
            "wake_port": port,
        },
        dry_run=dry_run,
        verbose=verbose,
    )


def start_guest(
    config: "YamlRoot", ref: NodeRef, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Start a Proxmox guest by running ``qm``/``pct`` on the node that hosts it."""
    parent: Optional[Parent] = ref.parent
    node: Node = ref.node
    # Unreachable via the CLI, which sends hosts down the packet path — but it also
    # narrows Node to the guest types, which are the ones carrying a vmid.
    if parent is None or isinstance(node, Host):
        raise ValueError(
            f"'{node.name}' is not a Proxmox guest, so there is no node to start "
            "it from. Wake it with a magic packet instead (give it a 'mac')."
        )

    creds: Creds = creds_for(parent, config.settings.default_creds)
    inventory: dict = {
        "all": {
            "hosts": {
                f"{_PARENT_ALIAS}_{parent.name}": ssh_host_vars(creds, str(parent.ip))
            }
        }
    }
    return run_playbook(
        playbook="wake/guest.yml",
        inventory=inventory,
        extravars={"wake_cli": guest_cli(ref), "wake_vmid": node.vmid},
        dry_run=dry_run,
        verbose=verbose,
    )
