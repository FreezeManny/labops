from pydantic import BaseModel, model_validator
from typing import Optional, Dict, Any
from ipaddress import IPv4Address

from .lxc import LXC
from .vm import VM
from .web_services import WebService
from .docker import Docker, StackEntry
from models.input_conf.host import Host
from models.input_conf.settings import Settings

class YamlRoot(BaseModel):
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

        def check_ips(node: object) -> None:
            # Check for an 'ip' attribute of type IPv4Address
            ip : IPv4Address | None = getattr(node, "ip", None)
            if isinstance(ip, IPv4Address):
                if ip in all_ips:
                    raise ValueError(f"Duplicate IP address found across configuration: '{ip}'")
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
                
        return self

    @model_validator(mode="after")
    def validate_unique_names(self) -> "YamlRoot":
        all_names = set()
        if self.hosts:
            for k, host in self.hosts.items():
                if k in all_names:
                    raise ValueError(f"Duplicate name found across configuration: '{k}'")
                all_names.add(k)

                if host.lxc:
                    for lxc_name in host.lxc.keys():
                        if lxc_name in all_names:
                            raise ValueError(f"Duplicate name found across configuration: '{lxc_name}'")
                        all_names.add(lxc_name)
                
                if host.vm:
                    for vm_name in host.vm.keys():
                        if vm_name in all_names:
                            raise ValueError(f"Duplicate name found across configuration: '{vm_name}'")
                        all_names.add(vm_name)
        return self

    @model_validator(mode="after")
    def validate_unique_proxy_names(self) -> "YamlRoot":
        """
        Ensures all web_services.proxy_name values are unique across the entire configuration (hosts, lxc, vm, docker stacks).
        """
        all_proxy_names: set[str] = set()
        def check_proxy_names(node: object) -> None:
            # Check for web_services
            web_services : WebService | None = getattr(node, "web_services", None)
            if web_services:
                for ws in getattr(web_services, "root", []):
                    proxy_name : str| None= getattr(ws, "proxy_name", None)
                    if proxy_name:
                        if proxy_name in all_proxy_names:
                            raise ValueError(f"Duplicate proxy_name found across configuration: '{proxy_name}'")
                        all_proxy_names.add(proxy_name)
            # Check for docker stacks
            docker :Docker | None= getattr(node, "docker", None)
            if docker:
                stacks: dict[str, StackEntry] = getattr(docker, "stacks", {})
                for stack in stacks.values():
                    stack_ws: WebService | None = getattr(stack, "web_services", None)
                    if stack_ws:
                        for ws in getattr(stack_ws, "root", []):
                            proxy_name: str | None = getattr(ws, "proxy_name", None)
                            if proxy_name:
                                if proxy_name in all_proxy_names:
                                    raise ValueError(f"Duplicate proxy_name found across configuration: '{proxy_name}'")
                                all_proxy_names.add(proxy_name)
            # Check for lxc and vm recursively
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
        return self