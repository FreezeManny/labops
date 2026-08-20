from pydantic import Field, model_validator
from typing import Iterator, Optional, Dict
from ipaddress import IPv4Address

from models.nodes import (
    NodeRef,
    Selector,
    WebServiceRef,
    find_node,
    iter_nodes,
    iter_web_services,
    node_dns_labels,
    select_nodes,
    unknown_under_names,
)

from .host import Host
from .proxy import AccessList
from .settings import Settings
from .custom_types import StrictModel
from .common_validators.hostname import validate_hostname_label


class YamlRoot(StrictModel):
    """The whole homelab config — the root of `homelab.yml`.

    Two blocks: `settings` for everything global, and `hosts` for the inventory
    tree. Unknown keys are rejected everywhere rather than ignored, so a typo is
    a validation error instead of a setting that silently never applied.
    """

    settings: Settings = Field(
        ..., description="Credentials, the secret store, DNS, proxy and target sets."
    )
    hosts: Optional[Dict[str, Host]] = Field(
        None,
        description=(
            "The inventory, keyed by node name. Proxmox hosts nest their guests "
            "underneath as `vm:` and `lxc:`, so this one block is the whole tree."
        ),
    )

    # ─── Asking the tree ──────────────────────────────────────────────────────
    #
    # The three shapes of that question — walk it, find one node, select a subset.
    # See models/nodes.py for the ordering, the record types and the matching rule.

    def iter_nodes(self) -> Iterator[NodeRef]:
        """Every host, VM and LXC in the config, at any depth."""
        return iter_nodes(self.hosts)

    def iter_web_services(self) -> Iterator[WebServiceRef]:
        """Every web_service in the config — each node's own and its stacks'."""
        return iter_web_services(self.hosts)

    def find_node(self, node_id: str, setting: Optional[str] = None) -> NodeRef:
        """The one node named by ``node_id`` — a name or IP."""
        return find_node(self.hosts, node_id, setting)

    def select(self, sel: Selector) -> list[NodeRef]:
        """The nodes a selector matches, in tree order. See models/nodes.py."""
        return select_nodes(self.hosts, sel)

    # ─── Validators ───────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def propagate_host_names(self) -> "YamlRoot":
        # The key names the host unless the host overrides it. Runs first, so
        # every later validator sees effective names rather than keys.
        if self.hosts:
            for k, host in self.hosts.items():
                if not host.name:
                    host.name = k
        return self

    @model_validator(mode="after")
    def validate_unique_ips(self) -> "YamlRoot":
        all_ips: set[IPv4Address] = set()
        errors: list[str] = []

        for ref in self.iter_nodes():
            ip: IPv4Address = ref.node.ip
            if ip in all_ips:
                errors.append(
                    f"Duplicate IP address found across configuration: '{ip}'"
                )
            else:
                all_ips.add(ip)

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_unique_macs(self) -> "YamlRoot":
        # Same reasoning as the IP check above, with a sharper failure: two nodes
        # sharing a MAC is a copy-paste, and `labops wake` would silently power on
        # whichever machine actually owns it.
        seen: dict[str, str] = {}
        errors: list[str] = []

        for ref in self.iter_nodes():
            mac: Optional[str] = ref.node.mac
            if mac is None:
                continue
            where: str = " → ".join(ref.path)
            if mac in seen:
                errors.append(
                    f"Duplicate MAC address found across configuration: '{mac}' "
                    f"is claimed by both '{seen[mac]}' and '{where}'."
                )
            else:
                seen[mac] = where

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_unique_names(self) -> "YamlRoot":
        """A node's name is how every command addresses it, so it must name one node.

        Tree-wide, not per level. This used to check hosts and their *direct*
        lxc/vm children only, and guests nested deeper were left to collide — which
        made a name an id that sometimes matched two machines, and every lookup
        carry a branch for it. Depth is not something a user states when they type
        a name, so it cannot be what makes one unambiguous.

        Checked on the *effective* name — the node's `name` where it set one,
        otherwise its key. Keys alone cannot collide, but an override can collide
        with another node's key or override. Runs after propagate_host_names and
        Host.propagate_lxc_vm_names, which are what populate `name`.

        Looks like validate_unique_dns_names below and is not redundant with it:
        that one sees published labels, and `dns_name` / `dns: false` take a node
        out of its view while leaving it perfectly addressable here.
        """
        owners: dict[str, str] = {}
        errors: list[str] = []

        for ref in self.iter_nodes():
            where: str = " → ".join(ref.path)
            name: str = ref.node.name
            if name in owners:
                errors.append(
                    f"Duplicate name found across configuration: '{name}' is "
                    f"claimed by both '{owners[name]}' and '{where}'."
                )
            else:
                owners[name] = where

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_unique_proxy_names(self) -> "YamlRoot":
        # A proxy_name becomes a hostname, so it must be unique across the whole
        # config — two services claiming one name is not resolvable.
        all_proxy_names: set[str] = set()
        errors: list[str] = []

        for ref in self.iter_web_services():
            proxy_name: Optional[str] = ref.web_service.proxy_name
            if not proxy_name:
                continue
            if proxy_name in all_proxy_names:
                errors.append(
                    f"Duplicate proxy_name found across configuration: '{proxy_name}'"
                )
            else:
                all_proxy_names.add(proxy_name)

        if errors:
            raise ValueError("\n".join(errors))

        return self

    # ─── DNS ──────────────────────────────────────────────────────────────────
    #
    # Both checks are gated on settings.dns: without it no records are derived, so
    # a name like 'proxmox_test' is inert and rejecting it would be noise. They run
    # after propagate_host_names, which is what populates node.name.

    @model_validator(mode="after")
    def validate_dns_node_names(self) -> "YamlRoot":
        """A published node name becomes a DNS label, so it must be a legal one.

        A node carrying an explicit ``dns_name`` is exempt — its own name is never
        published, so it may be anything (``proxmox_test``, a serial number).
        """
        if self.settings.dns is None:
            return self

        errors: list[str] = []
        for ref in self.iter_nodes():
            node = ref.node
            if not node.dns or node.dns_name:
                continue
            try:
                validate_hostname_label(
                    node.name, "node name", "settings.dns.local_dns_suffix"
                )
            except ValueError as e:
                errors.append(
                    f"{e} Rename the node, set 'dns_name' on it, or exclude it "
                    "with 'dns: false'."
                )

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_unique_dns_names(self) -> "YamlRoot":
        """Two nodes may not publish the same DNS label.

        Every record shares the one ``local_dns_suffix``, so duplicate labels are
        duplicate hostnames — a name resolving to two addresses, which is a typo
        far more often than it is intent.
        """
        if self.settings.dns is None:
            return self

        owners: dict[str, str] = {}
        errors: list[str] = []
        for ref in self.iter_nodes():
            where: str = " → ".join(ref.path)
            for label in node_dns_labels(ref.node):
                if label in owners:
                    errors.append(
                        f"Duplicate DNS name '{label}' found across configuration: "
                        f"claimed by both '{owners[label]}' and '{where}'."
                    )
                else:
                    owners[label] = where

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_target_names(self) -> "YamlRoot":
        """Every `under` in a named target set must name a real node.

        A named set is curated config that gets run months later, so a typo in
        it is invisible: the selection quietly matches nothing and the run looks
        like a success. Catch it at validation time instead. Ad-hoc CLI
        selectors get the same check at call time, where the error is immediate.
        """
        errors: list[str] = []

        for set_name, sel in self.settings.targets.items():
            for missing in unknown_under_names(self.hosts, sel.under):
                errors.append(
                    f"Target set '{set_name}' references unknown node "
                    f"'{missing}' in 'under'."
                )
            for missing in unknown_under_names(self.hosts, sel.exclude):
                errors.append(
                    f"Target set '{set_name}' references unknown node "
                    f"'{missing}' in 'exclude'."
                )

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_access_references(self) -> "YamlRoot":
        """
        Ensure every web_service is routable and its access lists are usable:
        - if any web_services exist, settings.proxy must be configured;
        - every name in a web_service's `access` is a key in
          settings.proxy.access_lists;
        - a service naming several lists names none that carries a `deny`.

        The last one is about what a union means. `access: [local, vpn]` unions
        both lists' `accept` *and* their `deny`, so `local`'s LAN-scoped deny
        would silently ban that address on the VPN route too — a statement about
        one network turned into a global one. Rather than guess, reject it.
        """
        errors: list[str] = []
        known_lists: dict[str, AccessList] = (
            self.settings.proxy.access_lists if self.settings.proxy else {}
        )
        has_web_services = False

        for ref in self.iter_web_services():
            has_web_services = True
            ws = ref.web_service
            where = " → ".join(ref.path)
            named = ws.access or []
            for name in named:
                if name not in known_lists:
                    errors.append(
                        f"web_service '{ws.proxy_name or ws.port}' on '{where}' references "
                        f"unknown access list '{name}'. Define it under "
                        f"settings.proxy.access_lists."
                    )
            if len(named) > 1:
                for name in named:
                    al = known_lists.get(name)
                    if al is not None and al.deny:
                        errors.append(
                            f"web_service '{ws.proxy_name or ws.port}' on '{where}' names "
                            f"several access lists, and '{name}' carries a 'deny'. A union "
                            f"applies that deny to every listed range, so it would block "
                            f"the address on routes it was never meant to cover. Give the "
                            f"service its own access list instead."
                        )

        if has_web_services and self.settings.proxy is None:
            errors.insert(
                0,
                "web_services are defined but settings.proxy is missing. "
                "Configure settings.proxy (proxy_suffix, access_lists, default_access) "
                "to route them.",
            )

        if errors:
            raise ValueError("\n".join(errors))

        return self
