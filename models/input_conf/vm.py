from pydantic import model_validator, DirectoryPath
from typing import Optional, Dict, Any, Literal
from ipaddress import IPv4Address

from .creds import Creds
from .web_services import WebServices
from .docker import Docker
from .lxc import LXC
from .custom_types import OSType, HostType, StrictModel
from .common_validators.web_services import check_duplicate_ws_ports
from .common_validators.managed import forbid_management_fields_when_unmanaged
from .common_validators.dns import DnsNames


class VM(StrictModel):
    name: str = ""
    type: HostType = "bare-metal"
    os: OSType
    ip: IPv4Address
    vmid: int
    creds: Optional[Creds] = None
    tags: list[str] = []
    lxc: Optional[Dict[str, LXC]] = None
    vm: Optional[Dict[str, "VM"]] = None  ## CHECK THIS
    web_services: Optional[WebServices] = None
    docker: Optional[Docker] = None
    dns: bool = True
    dns_name: DnsNames = None

    @model_validator(mode="after")
    def check_unmanaged_constraints(self) -> "VM":
        return forbid_management_fields_when_unmanaged(self)

    @model_validator(mode="after")
    def validate_ws_ports(self) -> "VM":
        return check_duplicate_ws_ports(self)

    @model_validator(mode="after")
    def propagate_lxc_vm_names(self) -> "VM":
        # Same as Host.propagate_lxc_vm_names: a nested child's dict key is its
        # name. Without this, LXCs/VMs under a VM keep the empty default and are
        # unaddressable by name (find) and unnamed in generated inventories.
        for k, v in (self.lxc or {}).items():
            v.name = k
        for k, v in (self.vm or {}).items():
            v.name = k
        return self


VMs = Dict[str, VM]
