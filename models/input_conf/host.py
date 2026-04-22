from pydantic import BaseModel, model_validator, DirectoryPath
from typing import Optional, Dict, Any, Literal
from ipaddress import IPv4Address

from .creds import Creds
from .web_services import WebServices
from .docker import Docker
from .lxc import LXCs
from .vm import VMs
from .custom_types import HostType, OSType

class Host(BaseModel):
    name: str = ""
    type: HostType = "bare-metal"
    os: OSType
    ip: IPv4Address
    creds: Optional[Creds] = None
    lxc: Optional[LXCs] = None
    vm: Optional[VMs] = None ## CHECK THIS
    web_services: Optional[WebServices] = None

    @model_validator(mode="after")
    def check_proxmox_support(self) -> "Host":
        if self.type != "proxmox":
            if self.lxc is not None or self.vm is not None:
                raise ValueError(
                    "Fields 'lxc' and 'vm' are only allowed when type is 'proxmox'"
                )
        return self

    @model_validator(mode="after")
    def propagate_lxc_vm_names(self) -> "Host":
        # Inject the dictionary key as the 'name' attribute for child LXCs
        if self.lxc:
            for k, v in self.lxc.items():
                v.name = k
                
        # Inject the dictionary key as the 'name' attribute for child VMs
        if self.vm:
            for k, v in self.vm.items():
                v.name = k
                
        return self
