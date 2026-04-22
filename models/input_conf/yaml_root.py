from pydantic import BaseModel, model_validator
from typing import Optional, Dict, Any
from ipaddress import IPv4Address

from .lxc import LXC
from .vm import VM
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