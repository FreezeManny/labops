from pydantic import BaseModel, model_validator, DirectoryPath
from typing import Optional, Dict, Any, Literal
from ipaddress import IPv4Address

from .creds import Creds
from .web_services import WebServices
from .docker import Docker
from .lxc import LXCs
from .vm import VMs
from .custom_types import HostType, OSType
from .common_validators.web_services import check_duplicate_ws_ports

class Host(BaseModel):
    name: str = ""
    type: HostType = "bare-metal"
    os: OSType
    ip: IPv4Address
    creds: Optional[Creds] = None
    lxc: Optional[LXCs] = None
    vm: Optional[VMs] = None
    docker: Optional[Docker]
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
    def check_duplicate_vmid(self) -> "Host":
        all_ids: set[int] = set()
        if self.lxc:
            for lxc_obj in self.lxc.values():
                if lxc_obj.vmid in all_ids:
                    raise ValueError(f"Duplicate vmid found: {lxc_obj.vmid}")
                all_ids.add(lxc_obj.vmid)
        if self.vm:
            for vm_obj in self.vm.values():
                if vm_obj.vmid in all_ids:
                    raise ValueError(f"Duplicate vmid found: {vm_obj.vmid}")
                all_ids.add(vm_obj.vmid)
        return self

    @model_validator(mode="after")
    def check_duplicate_ws_ports(self) -> "Host":
        return check_duplicate_ws_ports(self)

    @model_validator(mode="after")
    def propagate_lxc_vm_names(self) -> "Host":
        # Inject the dictionary key as the 'name' attribute for child LXCs
        if self.lxc:
            for k, v in self.lxc.items():
                v.name: str = k
                
        # Inject the dictionary key as the 'name' attribute for child VMs
        if self.vm:
            for k, v in self.vm.items():
                v.name: str = k
                
        return self
