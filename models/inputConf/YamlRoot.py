from pydantic import BaseModel, model_validator
from typing import Optional, Dict

from models.inputConf.hosts import Host
from models.inputConf.settings import Settings

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