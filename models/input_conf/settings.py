from pydantic import BaseModel, FilePath,  model_validator
from typing import Optional
from ipaddress import IPv4Address

from models.input_conf.creds import Creds

class Dns(BaseModel):
    local_dns_suffix: str
    pihole_location: IPv4Address


class Proxy(BaseModel):
    proxy_suffix: str
    proxy_location: IPv4Address


class Settings(BaseModel):
    default_creds: Creds
    dns: Optional[Dns] = None
    proxy: Optional[Proxy] = None
