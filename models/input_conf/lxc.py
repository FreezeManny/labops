from pydantic import BaseModel, DirectoryPath
from ipaddress import IPv4Address
from typing import Optional, Dict

from .hosts import OSType
from .creds import Creds
from .web_services import WebServices
from .docker import Docker

class LXC(BaseModel):
    name: str = ""
    ip: IPv4Address
    os: OSType
    vmid: int
    creds: Optional[Creds] = None
    web_services: Optional[WebServices] = None
    docker: Optional[Docker] = None

