from pydantic import BaseModel, model_validator, DirectoryPath
from typing import Optional, Dict, Any, Literal
from ipaddress import IPv4Address

from models.inputConf.creds import Creds

OSType = Literal["debian", "alpine", "redhat"]
HostType = Literal["bare-metal", "proxmox"]


class WebService(BaseModel):
    port: int
    proxy_name: Optional[str] = None


class DockerStack(BaseModel):
    config_path: DirectoryPath
    web_services: Optional[Dict[str, WebService]] = None


class LXC(BaseModel):
    name: str = ""
    ip: IPv4Address
    os: OSType
    vmid: int
    creds: Optional[Creds] = None
    web_services: Optional[Dict[str, WebService]] = None
    docker_stack: Optional[Dict[str, DockerStack]] = None

class Host(BaseModel):
    name: str = ""
    type: HostType = "bare-metal"
    os: OSType
    ip: IPv4Address
    creds: Optional[Creds] = None
    lxc: Optional[Dict[str, LXC]] = None
    vm: Optional[Dict[str, "Host"]] = None ## CHECK THIS
    web_services: Optional[Dict[str, WebService]] = None

    @model_validator(mode="after")
    def check_proxmox_support(self) -> "Host":
        if self.type != "proxmox":
            if self.lxc is not None or self.vm is not None:
                raise ValueError(
                    "Fields 'lxc' and 'vm' are only allowed when type is 'proxmox'"
                )
        return self

    @model_validator(mode="after")
    def propagate_lxc_vm_names(self) -> "Host":
        # Inject the dictionary key as the 'name' attribute for child LXCs
        if self.lxc:
            for k, v in self.lxc.items():
                v.name = k
                
        # Inject the dictionary key as the 'name' attribute for child VMs
        if self.vm:
            for k, v in self.vm.items():
                v.name = k
                
        return self
