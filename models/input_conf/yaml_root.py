from pydantic import model_validator
from typing import Optional, Dict, Any
from ipaddress import IPv4Address

from .lxc import LXC
from .vm import VM
from .web_services import WebService, WebServices
from .docker import Docker, StackEntry
from .host import Host
from .settings import Settings
from .custom_types import StrictModel


class YamlRoot(StrictModel):
    settings: Settings
    hosts: Optional[Dict[str, Host]] = None

    @model_validator(mode="after")
    def propagate_host_names(self) -> "YamlRoot":
        if self.hosts:
            for k, host in self.hosts.items():
                host.name = k
        return self

    @model_validator(mode="after")
    def validate_unique_ips(self) -> "YamlRoot":

        all_ips: set[IPv4Address] = set()
        errors: list[str] = []

        def check_ips(node: object) -> None:
            # Check for an 'ip' attribute of type IPv4Address
            ip: IPv4Address | None = getattr(node, "ip", None)
            if isinstance(ip, IPv4Address):
                if ip in all_ips:
                    errors.append(
                        f"Duplicate IP address found across configuration: '{ip}'"
                    )
                else:
                    all_ips.add(ip)
            # Check for lxc and vm attributes that are dict-like
            lxc: LXC | None = getattr(node, "lxc", None)
            if isinstance(lxc, dict):
                for lxc_node in lxc.values():
                    check_ips(lxc_node)
            vm: VM | None = getattr(node, "vm", None)
            if isinstance(vm, dict):
                for vm_node in vm.values():
                    check_ips(vm_node)

        if self.hosts:
            for host in self.hosts.values():
                check_ips(host)

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_unique_names(self) -> "YamlRoot":
        all_names: set[str] = set()
        errors: list[str] = []

        if self.hosts:
            for k, host in self.hosts.items():
                if k in all_names:
                    errors.append(f"Duplicate name found across configuration: '{k}'")
                else:
                    all_names.add(k)

                if host.lxc:
                    for lxc_name in host.lxc.keys():
                        if lxc_name in all_names:
                            errors.append(
                                f"Duplicate name found across configuration: '{lxc_name}'"
                            )
                        else:
                            all_names.add(lxc_name)

                if host.vm:
                    for vm_name in host.vm.keys():
                        if vm_name in all_names:
                            errors.append(
                                f"Duplicate name found across configuration: '{vm_name}'"
                            )
                        else:
                            all_names.add(vm_name)

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_unique_proxy_names(self) -> "YamlRoot":
        all_proxy_names: set[str] = set()
        errors: list[str] = []

        def check_proxy_names(node: object) -> None:
            web_services: WebService | None = getattr(node, "web_services", None)
            if web_services:
                for ws in getattr(web_services, "root", []):
                    proxy_name: str | None = getattr(ws, "proxy_name", None)
                    if proxy_name:
                        if proxy_name in all_proxy_names:
                            errors.append(
                                f"Duplicate proxy_name found across configuration: '{proxy_name}'"
                            )
                        else:
                            all_proxy_names.add(proxy_name)
            docker: Docker | None = getattr(node, "docker", None)
            if docker:
                stacks: dict[str, StackEntry] = getattr(docker, "stacks", {})
                for stack in stacks.values():
                    stack_ws: WebService | None = getattr(stack, "web_services", None)
                    if stack_ws:
                        for ws in getattr(stack_ws, "root", []):
                            proxy_name = getattr(ws, "proxy_name", None)
                            if proxy_name:
                                if proxy_name in all_proxy_names:
                                    errors.append(
                                        f"Duplicate proxy_name found across configuration: '{proxy_name}'"
                                    )
                                else:
                                    all_proxy_names.add(proxy_name)
            lxc: LXC | None = getattr(node, "lxc", None)
            if isinstance(lxc, dict):
                for lxc_node in lxc.values():
                    check_proxy_names(lxc_node)
            vm: VM | None = getattr(node, "vm", None)
            if isinstance(vm, dict):
                for vm_node in vm.values():
                    check_proxy_names(vm_node)

        if self.hosts:
            for host in self.hosts.values():
                check_proxy_names(host)

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @model_validator(mode="after")
    def validate_access_references(self) -> "YamlRoot":
        """
        Ensure every web_service is routable and its access lists are defined:
        - if any web_services exist, settings.proxy must be configured;
        - every name in a web_service's `access` is a key in
          settings.proxy.access_lists.
        """
        errors: list[str] = []
        known_lists: set[str] = (
            set(self.settings.proxy.access_lists) if self.settings.proxy else set()
        )
        has_web_services = False

        def check_access(node: object) -> None:
            nonlocal has_web_services

            def check_ws(ws_container: WebServices | None) -> None:
                nonlocal has_web_services
                if not ws_container:
                    return
                for ws in ws_container.root:
                    has_web_services = True
                    for name in ws.access or []:
                        if name not in known_lists:
                            errors.append(
                                f"web_service '{ws.proxy_name or ws.port}' references unknown "
                                f"access list '{name}'. Define it under settings.proxy.access_lists."
                            )

            check_ws(getattr(node, "web_services", None))
            docker: Docker | None = getattr(node, "docker", None)
            if docker:
                for stack in getattr(docker, "stacks", {}).values():
                    check_ws(getattr(stack, "web_services", None))

            lxc: LXC | None = getattr(node, "lxc", None)
            if isinstance(lxc, dict):
                for lxc_node in lxc.values():
                    check_access(lxc_node)
            vm: VM | None = getattr(node, "vm", None)
            if isinstance(vm, dict):
                for vm_node in vm.values():
                    check_access(vm_node)

        if self.hosts:
            for host in self.hosts.values():
                check_access(host)

        if has_web_services and self.settings.proxy is None:
            errors.insert(
                0,
                "web_services are defined but settings.proxy is missing. "
                "Configure settings.proxy (proxy_suffix, proxy_location, access_lists) to route them.",
            )

        if errors:
            raise ValueError("\n".join(errors))

        return self
