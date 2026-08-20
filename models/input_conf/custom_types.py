from typing import Literal
from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# "unmanaged" is the catch-all for any OS labops doesn't manage — an appliance
# (HomeAssistant OS), an unsupported distro (NixOS), or simply a box you don't
# own. Such nodes keep ip/web_services but are skipped by update/setup. The
# managed set (with update playbooks) is debian/alpine/redhat.
OSType = Literal["debian", "alpine", "redhat", "unmanaged"]
# Whether a node virtualizes, and with what. Not "what kind of hardware this is":
# a VM carries the same field, and would have to call itself bare metal to say it
# hosts no guests of its own. `proxmox` is what unlocks the `lxc:`/`vm:` blocks.
Hypervisor = Literal["none", "proxmox"]

# The single source of truth for the "unmanaged" sentinel — import this instead
# of hard-coding the string when checking whether a node is managed.
UNMANAGED_OS: OSType = "unmanaged"
