"""Validator shared by Host/VM for the `lxc:` and `vm:` blocks.

Guests hang off a node only when that node runs a hypervisor, and today that
means Proxmox: `pct_host_vars` (src/utils/inventory.py) reaches a container with
``community.proxmox.proxmox_pct_remote``, and `labops wake` starts a guest with
``pct``/``qm``. So the blocks are gated on ``hypervisor: proxmox`` rather than on
"not none" — should a second hypervisor ever be added, it must opt into LXC
support explicitly instead of inheriting it.

Both Host and VM carry the field and both nest guests, so the rule lives here:
it used to sit on Host alone, and a VM with ``hypervisor`` unset plus an ``lxc:``
block validated silently.
"""

from typing import TypeVar

T = TypeVar("T")


def forbid_guests_without_proxmox(obj: T) -> T:
    if getattr(obj, "hypervisor", None) != "proxmox":
        if (
            getattr(obj, "lxc", None) is not None
            or getattr(obj, "vm", None) is not None
        ):
            raise ValueError(
                "Fields 'lxc' and 'vm' are only allowed when hypervisor is 'proxmox'"
            )
    return obj
