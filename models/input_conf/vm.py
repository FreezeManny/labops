
from pydantic import BaseModel, model_validator, DirectoryPath
from typing import Optional, Dict, Any, Literal
from ipaddress import IPv4Address

from .creds import Creds
from .web_services import WebServices
from .docker import Docker
from .lxc import LXC
from .custom_types import OSType, HostType
from .common_validators.web_services import check_duplicate_ws_ports

class VM(BaseModel):
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
    def validate_ws_ports(self) -> "VM":
        return check_duplicate_ws_ports(self)


VMs = Dict[str, VM]