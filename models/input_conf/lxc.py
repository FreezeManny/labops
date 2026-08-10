from pydantic import DirectoryPath, model_validator
from pydantic_extra_types.mac_address import MacAddress
from ipaddress import IPv4Address
from typing import Optional, Dict

from .creds import Creds
from .web_services import WebServices
from .docker import Docker

from .custom_types import OSType, StrictModel
from .common_validators.web_services import check_duplicate_ws_ports
from .common_validators.managed import forbid_management_fields_when_unmanaged
from .common_validators.dns import DnsNames


class LXC(StrictModel):
    name: str = ""
    ip: IPv4Address
    os: OSType
    vmid: int
    creds: Optional[Creds] = None
    tags: list[str] = []
    web_services: Optional[WebServices] = None
    docker: Optional[Docker] = None
    dns: bool = True
    dns_name: DnsNames = None
    mac: Optional[MacAddress] = None

    @model_validator(mode="after")
    def check_unmanaged_constraints(self) -> "LXC":
        return forbid_management_fields_when_unmanaged(self)

    @model_validator(mode="after")
    def validate_ws_ports(self) -> "LXC":
        return check_duplicate_ws_ports(self)


LXCs = Dict[str, LXC]
