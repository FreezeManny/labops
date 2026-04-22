from pydantic import DirectoryPath, model_validator
from ipaddress import IPv4Address
from typing import Optional, Dict

from .creds import Creds
from .web_services import WebServices
from .docker import Docker

from .custom_types import OSType, StrictModel
from .common_validators.web_services import check_duplicate_ws_ports

class LXC(StrictModel):
    name: str = ""
    ip: IPv4Address
    os: OSType
    vmid: int
    creds: Optional[Creds] = None
    web_services: Optional[WebServices] = None
    docker: Optional[Docker] = None

    @model_validator(mode="after")
    def validate_ws_ports(self) -> "LXC":
        return check_duplicate_ws_ports(self)

LXCs = Dict[str, LXC]