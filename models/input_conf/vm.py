from pydantic import Field, model_validator
from pydantic_extra_types.mac_address import MacAddress
from typing import Optional, Dict, Any, Literal
from ipaddress import IPv4Address

from .creds import Creds
from .web_services import WebServices
from .docker import Docker
from .lxc import LXC
from .custom_types import OSType, HostType, StrictModel
from .common_validators.web_services import check_duplicate_ws_ports
from .common_validators.managed import forbid_management_fields_when_unmanaged
from .common_validators.proxmox import forbid_guests_without_proxmox
from .common_validators.dns import DnsNames


class VM(StrictModel):
    """A Proxmox virtual machine, written under a `proxmox` node's `vm:` block.

    Unlike a container, a VM is reached over SSH like an ordinary host, so it
    behaves the same as a `hosts:` entry apart from carrying a `vmid` and
    belonging to a parent. An appliance OS that labops cannot provision —
    HomeAssistant OS is the standing example — is still a VM, written with
    `os: unmanaged`.
    """

    name: str = Field(
        "",
        description=(
            "Overrides the key this VM is written under. Leave it unset — the "
            "usual case — and the key is the name. Set it when the key is not the "
            "name you want to target and publish, e.g. a key that is not a legal "
            "DNS label. Must be unique across the config either way."
        ),
    )
    type: HostType = Field(
        "bare-metal",
        description=(
            "`proxmox` if this guest is itself a Proxmox node with guests of its "
            "own (nested virtualisation). Otherwise leave it."
        ),
    )
    os: OSType = Field(
        ...,
        description=(
            "Picks the package manager used to update this VM: `debian` (apt), "
            "`alpine` (apk) or `redhat` (dnf). Use `unmanaged` for an appliance "
            "OS labops cannot patch or SSH-provision — it stays listed, resolved "
            "and proxied, but setup/update skip it."
        ),
    )
    ip: IPv4Address = Field(
        ...,
        description=(
            "The address labops connects to over SSH, and the address published "
            "for this VM's DNS records and proxy routes."
        ),
    )
    vmid: int = Field(
        ...,
        description=(
            "The Proxmox VM ID. Used to start the guest (`qm start <vmid>` on the "
            "parent) and to address it by number, so it must match Proxmox and be "
            "unique across the guests of one host."
        ),
    )
    creds: Optional[Creds] = Field(
        None,
        description=(
            "Credentials for this VM only. Omit to use `settings.default_creds`."
        ),
    )
    tags: list[str] = Field(
        [],
        description=(
            "Free-form labels, matched by `labops update --tag`. Not inherited "
            "from the parent host."
        ),
    )
    lxc: Optional[Dict[str, LXC]] = Field(
        None,
        description=(
            "Containers on this VM, when it is itself a Proxmox node. Keyed by name."
        ),
    )
    vm: Optional[Dict[str, "VM"]] = Field(
        None,
        description=(
            "Virtual machines on this VM, when it is itself a Proxmox node. "
            "Keyed by name."
        ),
    )
    web_services: Optional[WebServices] = Field(
        None,
        description=(
            "HTTP services this VM exposes. Each entry with a `proxy_name` "
            "becomes a route in the generated Caddyfile."
        ),
    )
    docker: Optional[Docker] = Field(
        None, description="Docker Compose stacks running on this VM."
    )
    dns: bool = Field(
        True, description="Set `false` to keep this VM out of DNS entirely."
    )
    dns_name: DnsNames = Field(
        None,
        description=(
            "Publish this VM under a different label than its key, or under "
            "several. Also exempts the key from having to be a legal DNS label."
        ),
    )
    mac: Optional[MacAddress] = Field(
        None,
        description=(
            "Not needed to wake a guest: `labops wake` runs `qm start <vmid>` on "
            "the parent, because a magic packet cannot start a stopped VM — "
            "nothing inside it is listening, and Proxmox does not watch for WoL "
            "on a guest's behalf. Set this only if the VM has a NIC of its own "
            "that really does wake, then ask for it with `wake --packet`."
        ),
    )

    @model_validator(mode="after")
    def check_proxmox_support(self) -> "VM":
        return forbid_guests_without_proxmox(self)

    @model_validator(mode="after")
    def check_unmanaged_constraints(self) -> "VM":
        return forbid_management_fields_when_unmanaged(self)

    @model_validator(mode="after")
    def validate_ws_ports(self) -> "VM":
        return check_duplicate_ws_ports(self)

    @model_validator(mode="after")
    def propagate_lxc_vm_names(self) -> "VM":
        # Same as Host.propagate_lxc_vm_names: a nested child's dict key is its
        # name, unless the child set one itself. Without this, LXCs/VMs under a
        # VM keep the empty default and are unaddressable by name (find) and
        # unnamed in generated inventories.
        for k, v in (self.lxc or {}).items():
            if not v.name:
                v.name = k
        for k, v in (self.vm or {}).items():
            if not v.name:
                v.name = k
        return self


VMs = Dict[str, VM]
