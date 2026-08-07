from pydantic import model_validator, DirectoryPath
from typing import Optional, Dict, Any, Literal
from ipaddress import IPv4Address

from .creds import Creds
from .web_services import WebServices
from .docker import Docker
from .lxc import LXCs
from .vm import VMs
from .custom_types import HostType, OSType, StrictModel
from .common_validators.web_services import check_duplicate_ws_ports
from .common_validators.managed import forbid_management_fields_when_unmanaged
from .common_validators.dns import DnsNames
from .common_validators.mac import MacAddress


class Host(StrictModel):
    name: str = ""
    type: HostType = "bare-metal"
    os: OSType
    ip: IPv4Address
    creds: Optional[Creds] = None
    tags: list[str] = []
    lxc: Optional[LXCs] = None
    vm: Optional[VMs] = None
    docker: Optional[Docker] = None
    web_services: Optional[WebServices] = None
    dns: bool = True
    dns_name: DnsNames = None
    mac: MacAddress = None

    @model_validator(mode="after")
    def check_proxmox_support(self) -> "Host":
        if self.type != "proxmox":
            if self.lxc is not None or self.vm is not None:
                raise ValueError(
                    "Fields 'lxc' and 'vm' are only allowed when type is 'proxmox'"
                )
        return self

    @model_validator(mode="after")
    def check_unmanaged_constraints(self) -> "Host":
        return forbid_management_fields_when_unmanaged(self)

    @model_validator(mode="after")
    def check_duplicate_vmid(self) -> "Host":
        all_ids: set[int] = set()
        errors: list[str] = []
        if self.lxc:
            for lxc_obj in self.lxc.values():
                if lxc_obj.vmid in all_ids:
                    errors.append(f"Duplicate vmid found: {lxc_obj.vmid}")
                else:
                    all_ids.add(lxc_obj.vmid)
        if self.vm:
            for vm_obj in self.vm.values():
                if vm_obj.vmid in all_ids:
                    errors.append(f"Duplicate vmid found: {vm_obj.vmid}")
                else:
                    all_ids.add(vm_obj.vmid)
        if errors:
            raise ValueError("\n".join(errors))
        return self

    @model_validator(mode="after")
    def check_duplicate_ws_ports(self) -> "Host":
        return check_duplicate_ws_ports(self)

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
