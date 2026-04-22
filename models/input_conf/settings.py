from pydantic import FilePath, model_validator
from typing import Optional
from ipaddress import IPv4Address

from models.input_conf.creds import Creds
from models.input_conf.custom_types import StrictModel

class Dns(StrictModel):
    local_dns_suffix: str
    pihole_location: IPv4Address


class Proxy(StrictModel):
    proxy_suffix: str
    proxy_location: IPv4Address


class Settings(StrictModel):
    default_creds: Creds
    dns: Optional[Dns] = None
    proxy: Optional[Proxy] = None
