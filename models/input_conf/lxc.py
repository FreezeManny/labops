from pydantic import Field, model_validator
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
    """A Proxmox container, written under a `proxmox` node's `lxc:` block.

    Containers are never reached over SSH: labops runs commands on the Proxmox
    parent and enters the container with `pct exec`. So an LXC needs no sshd and
    no route from the machine running labops — only a `vmid` and a reachable
    parent. That is also why `creds` here is rarely needed.
    """

    name: str = Field(
        "",
        description=(
            "Overrides the key this container is written under. Leave it unset — "
            "the usual case — and the key is the name. Set it when the key is not "
            "the name you want to target and publish, e.g. a key that is not a "
            "legal DNS label. Must be unique across the config either way."
        ),
    )
    ip: IPv4Address = Field(
        ...,
        description=(
            "The container's address, published for its DNS records and proxy "
            "routes. Not used to connect — that goes through the Proxmox parent."
        ),
    )
    os: OSType = Field(
        ...,
        description=(
            "Picks the package manager used to update this container: `debian` "
            "(apt), `alpine` (apk) or `redhat` (dnf). Use `unmanaged` to keep it "
            "listed and routable but never patched."
        ),
    )
    vmid: int = Field(
        ...,
        description=(
            "The Proxmox container ID. This is how labops addresses it — "
            "`pct exec <vmid>` on the parent — so it must match Proxmox, and it "
            "must be unique across the guests of one host."
        ),
    )
    creds: Optional[Creds] = Field(
        None,
        description=(
            "Credentials for this container only. Rarely needed: labops reaches "
            "it through the Proxmox parent, whose credentials are what matter."
        ),
    )
    tags: list[str] = Field(
        [],
        description=(
            "Free-form labels, matched by `labops update --tag`. Not inherited "
            "from the parent host — a container is only `prod` if it says so."
        ),
    )
    web_services: Optional[WebServices] = Field(
        None,
        description=(
            "HTTP services this container exposes. Each entry with a "
            "`proxy_name` becomes a route in the generated Caddyfile."
        ),
    )
    docker: Optional[Docker] = Field(
        None, description="Docker Compose stacks running in this container."
    )
    dns: bool = Field(
        True, description="Set `false` to keep this container out of DNS entirely."
    )
    dns_name: DnsNames = Field(
        None,
        description=(
            "Publish this container under a different label than its key, or "
            "under several. Also exempts the key from having to be a legal DNS "
            "label."
        ),
    )
    mac: Optional[MacAddress] = Field(
        None,
        description=(
            "Rarely useful here: a stopped container has nothing listening for a "
            "magic packet, so `labops wake` starts it with `pct start` on the "
            "parent instead. Set this only if the container really does own a "
            "NIC that wakes, and ask for it with `wake --packet`."
        ),
    )

    @model_validator(mode="after")
    def check_unmanaged_constraints(self) -> "LXC":
        return forbid_management_fields_when_unmanaged(self)

    @model_validator(mode="after")
    def validate_ws_ports(self) -> "LXC":
        return check_duplicate_ws_ports(self)


LXCs = Dict[str, LXC]
