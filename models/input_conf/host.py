from pydantic import Field, model_validator
from pydantic_extra_types.mac_address import MacAddress
from typing import Optional, Dict, Any, Literal
from ipaddress import IPv4Address

from .creds import Creds
from .web_services import WebServices
from .docker import Docker
from .lxc import LXCs
from .vm import VMs
from .custom_types import HostType, OSType, StrictModel
from .common_validators.web_services import check_duplicate_ws_ports
from .common_validators.managed import forbid_management_fields_when_unmanaged
from .common_validators.dns import DnsNames


class Host(StrictModel):
    """A top-level node under `hosts:` — anything labops reaches directly.

    A bare-metal box, an appliance you only want tracked, or a Proxmox node whose
    guests hang off it as `vm:` and `lxc:`. The key you write in `hosts:` is the
    node's name, and it becomes a DNS label when `settings.dns` is configured, so
    it must be a legal one (no underscores) unless `dns_name` overrides it.
    """

    name: str = Field(
        "",
        description=(
            "Filled in from the key this node is written under; do not set it. "
            "Present so code that receives a node still knows what it is called."
        ),
    )
    type: HostType = Field(
        "bare-metal",
        description=(
            "`proxmox` unlocks the `vm:` and `lxc:` blocks and makes this node "
            "the parent that guest commands run through. `bare-metal` is "
            "anything else."
        ),
    )
    os: OSType = Field(
        ...,
        description=(
            "Picks the package manager used to update this node: `debian` (apt), "
            "`alpine` (apk) or `redhat` (dnf). Use `unmanaged` for anything "
            "labops should not provision or patch — an appliance, an unsupported "
            "distro, or a box you do not own. Unmanaged nodes are still listed, "
            "resolved and proxied."
        ),
    )
    ip: IPv4Address = Field(
        ...,
        description=(
            "The address labops connects to, and the address published for this "
            "node's DNS records and proxy routes."
        ),
    )
    creds: Optional[Creds] = Field(
        None,
        description=(
            "Credentials for this node only. Omit to use `settings.default_creds`."
        ),
    )
    tags: list[str] = Field(
        [],
        description=(
            "Free-form labels, matched by `labops update --tag`. Tags are local "
            "to the node that carries them — a guest does not inherit its "
            "parent's tags, so use `--under` to sweep a whole subtree."
        ),
    )
    lxc: Optional[LXCs] = Field(
        None,
        description=(
            "Proxmox containers on this node, keyed by name. Requires "
            "`type: proxmox`."
        ),
    )
    vm: Optional[VMs] = Field(
        None,
        description=(
            "Proxmox virtual machines on this node, keyed by name. Requires "
            "`type: proxmox`."
        ),
    )
    docker: Optional[Docker] = Field(
        None, description="Docker Compose stacks running on this node."
    )
    web_services: Optional[WebServices] = Field(
        None,
        description=(
            "HTTP services this node exposes. Each entry with a `proxy_name` "
            "becomes a route in the generated Caddyfile."
        ),
    )
    dns: bool = Field(
        True,
        description=(
            "Set `false` to keep this node out of DNS entirely — tracked in the "
            "config, never published to Pi-hole."
        ),
    )
    dns_name: DnsNames = Field(
        None,
        description=(
            "Publish this node under a different label than its key, or under "
            "several: a list yields one record per name, all pointing at the "
            "same address. A node with `dns_name` is exempt from the rule that "
            "its key must be a legal DNS label."
        ),
    )
    mac: Optional[MacAddress] = Field(
        None,
        description=(
            "The NIC that listens for a Wake-on-LAN magic packet, needed by "
            "`labops wake`. Colon, dash and dotted notation are all accepted. A "
            "magic packet goes to the broadcast address, which routers do not "
            "forward, so run labops on the same segment or relay it with "
            "`wake --via`."
        ),
    )

    @model_validator(mode="after")
    def check_proxmox_support(self) -> "Host":
        if self.type != "proxmox":
            if self.lxc is not None or self.vm is not None:
                raise ValueError(
                    "Fields 'lxc' and 'vm' are only allowed when type is 'proxmox'"
                )
        return self

    @model_validator(mode="after")
    def check_unmanaged_constraints(self) -> "Host":
        return forbid_management_fields_when_unmanaged(self)

    @model_validator(mode="after")
    def check_duplicate_vmid(self) -> "Host":
        """A vmid addresses a guest on this Proxmox node, so it must address one.

        Per node rather than tree-wide, because that is Proxmox's own scope: a
        guest under a *nested* Proxmox lives in a different id space and may reuse
        the number freely.

        Names both claimants, like every other uniqueness check here. `lxc:` and
        `vm:` share one id space, so the pair is often one of each — and the bare
        "Duplicate vmid found: 100" left you to work out which two those were.
        """
        owners: dict[int, str] = {}
        errors: list[str] = []

        # The key is the guest's name unless it overrode it; `propagate_lxc_vm_names`
        # runs after this validator, so the fallback is not decoration.
        for kind, guests in (("lxc", self.lxc), ("vm", self.vm)):
            for key, guest in (guests or {}).items():
                where: str = f"{kind} '{guest.name or key}'"
                if guest.vmid in owners:
                    errors.append(
                        f"Duplicate vmid found: {guest.vmid} is claimed by both "
                        f"{owners[guest.vmid]} and {where}."
                    )
                else:
                    owners[guest.vmid] = where

        if errors:
            raise ValueError("\n".join(errors))
        return self

    @model_validator(mode="after")
    def check_duplicate_ws_ports(self) -> "Host":
        return check_duplicate_ws_ports(self)

    @model_validator(mode="after")
    def propagate_lxc_vm_names(self) -> "Host":
        # The dictionary key is the child's name — unless the child set one
        # itself, which overrides it. Filling in only the blanks is what makes
        # `name` a real field rather than one that silently swallows input.
        if self.lxc:
            for k, v in self.lxc.items():
                if not v.name:
                    v.name = k

        if self.vm:
            for k, v in self.vm.items():
                if not v.name:
                    v.name = k

        return self
