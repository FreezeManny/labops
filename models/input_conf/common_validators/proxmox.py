"""Validator shared by Host/VM for the `lxc:` and `vm:` blocks.

Guests hang off a node only when that node runs Proxmox: `pct_host_vars`
(src/utils/inventory.py) reaches a container with
``community.proxmox.proxmox_pct_remote``, and `labops wake` starts a guest with
``pct``/``qm``. So the blocks are gated on ``proxmox`` specifically rather than on
"not bare metal" — should a second hypervisor ever be supported, it must opt into
guest support explicitly instead of inheriting it.

Both Host and VM carry the field and both nest guests, so the rule lives here. It
used to sit on Host alone: a VM with ``lxc:`` and no Proxmox declared validated
silently, while the identical config on a Host was rejected.
"""

from typing import TypeVar

T = TypeVar("T")


def forbid_guests_without_proxmox(obj: T) -> T:
    if getattr(obj, "type", None) != "proxmox":
        if (
            getattr(obj, "lxc", None) is not None
            or getattr(obj, "vm", None) is not None
        ):
            raise ValueError(
                "Fields 'lxc' and 'vm' are only allowed when type is 'proxmox'"
            )
    return obj
