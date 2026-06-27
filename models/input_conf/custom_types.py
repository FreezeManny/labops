from typing import Literal
from pydantic import BaseModel, ConfigDict

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

# "unmanaged" is the catch-all for any OS labops doesn't manage — an appliance
# (HomeAssistant OS), an unsupported distro (NixOS), or simply a box you don't
# own. Such nodes keep ip/web_services but are skipped by update/setup. The
# managed set (with update playbooks) is debian/alpine/redhat.
OSType = Literal["debian", "alpine", "redhat", "unmanaged"]
HostType = Literal["bare-metal", "proxmox"]

