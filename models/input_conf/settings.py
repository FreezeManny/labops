from pydantic import FilePath, model_validator
from typing import Optional, Dict, List
from ipaddress import IPv4Address

from pydantic import IPvAnyNetwork

from models.input_conf.creds import Creds
from models.input_conf.custom_types import StrictModel

class Dns(StrictModel):
    local_dns_suffix: str
    pihole_location: IPv4Address


class AccessList(StrictModel):
    default: bool = False
    accept: List[IPvAnyNetwork]
    deny: Optional[List[IPvAnyNetwork]] = None

    @model_validator(mode="after")
    def validate_accept_non_empty(self) -> "AccessList":
        if not self.accept:
            raise ValueError("an access list must define at least one 'accept' CIDR.")
        return self


class Proxy(StrictModel):
    proxy_suffix: str
    proxy_location: IPv4Address
    caddyfile_path_remote: str = "/etc/caddy/Caddyfile"
    access_lists: Dict[str, AccessList]

    @model_validator(mode="after")
    def validate_access_lists(self) -> "Proxy":
        defaults: list[str] = [name for name, al in self.access_lists.items() if al.default]
        if len(defaults) == 0:
            raise ValueError(
                "settings.proxy.access_lists must mark exactly one list as 'default: true' "
                "(used for web_services with no explicit 'access')."
            )
        if len(defaults) > 1:
            raise ValueError(
                "only one access list may be 'default: true'; found: " + ", ".join(defaults)
            )
        return self

    @property
    def default_access_list(self) -> str:
        return next(name for name, al in self.access_lists.items() if al.default)


class Settings(StrictModel):
    default_creds: Creds
    dns: Optional[Dns] = None
    proxy: Optional[Proxy] = None
