from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Optional


@dataclass
class RouteResult:
    """A single reverse-proxy route derived from a web_service entry."""

    proxy_name: str  # subdomain label; hostname = proxy_name + proxy_suffix
    target_ip: IPv4Address  # IP of the node the web_service lives on
    port: int  # upstream port on target_ip
    access: Optional[
        list[str]
    ]  # access-list names (union); None -> local; ["public"] -> open
    path: list[str]  # node path for diagnostics, e.g. ["cprox", "home"]
