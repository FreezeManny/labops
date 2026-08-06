from typing import Dict, Optional
from ipaddress import IPv4Address

from models.input_conf.creds import Creds
from models.input_conf.custom_types import StrictModel
from models.input_conf.proxy import Proxy
from models.select import Selector


class Dns(StrictModel):
    local_dns_suffix: str
    pihole_location: IPv4Address


class Settings(StrictModel):
    default_creds: Creds
    # labops secret store (API tokens, etc.). Defaults to a `.env` next to the
    # config file; set this to point elsewhere (relative to the config file, or
    # absolute). The file itself is never committed (.gitignore).
    env_file: Optional[str] = None
    dns: Optional[Dns] = None
    proxy: Optional[Proxy] = None
    targets: Dict[str, Selector] = {}
