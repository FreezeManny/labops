from models.input_conf.yaml_root import YamlRoot
from models.input_conf.vm import VM


def findAll(config: YamlRoot) -> list[VM]:
    if config.hosts is None:
        raise KeyError("No hosts are defined in the configuration.")
    
    vms: list[VM] = []
    for host in config.hosts.values():
        if host.vm is not None:
            vms.extend(host.vm.values())
    return vms

def find(config: YamlRoot, targets: list[str]) -> list[VM]:
    if config.hosts is None:
        raise KeyError("No hosts are defined in the configuration.")
        
    all_vms: dict[str, VM] = {}
    for host in config.hosts.values():
        if host.vm is not None:
            all_vms.update(host.vm)
            
    found_vms: list[VM] = []
    for target in targets:
        found = False
        if target in all_vms:
            found_vms.append(all_vms[target])
            found = True
        else:
            for vm in all_vms.values():
                if str(vm.ip) == target:
                    found_vms.append(vm)
                    found = True
                    break
        
        if not found:
            raise KeyError(f"VM '{target}' was not found in the configuration by name or IP.")
            
    return found_vms