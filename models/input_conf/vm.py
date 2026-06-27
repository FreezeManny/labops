
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

class VM(StrictModel):
    name: str = ""
    type: HostType = "bare-metal"
    os: OSType
    ip: IPv4Address
    vmid: int
    creds: Optional[Creds] = None
    lxc: Optional[Dict[str, LXC]] = None
    vm: Optional[Dict[str, "VM"]] = None ## CHECK THIS
    web_services: Optional[WebServices] = None
    docker: Optional[Docker] = None

    @model_validator(mode="after")
    def check_unmanaged_constraints(self) -> "VM":
        return forbid_management_fields_when_unmanaged(self)

    @model_validator(mode="after")
    def validate_ws_ports(self) -> "VM":
        return check_duplicate_ws_ports(self)


VMs = Dict[str, VM]