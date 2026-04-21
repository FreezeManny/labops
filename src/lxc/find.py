from src.utils.ansible_runner import run_playbook
from models.inputConf.YamlRoot import YamlRoot
from models.inputConf.hosts import Host, LXC

def findAll(config: YamlRoot) -> list[tuple[Host, LXC]]:
    """Returns a list of all LXCs found inside Proxmox hosts in the Yaml config."""
    results = []
    if config.hosts is None:
        return results
        
    for host in config.hosts.values():
        if host.type == "proxmox" and host.lxc is not None:
            for lxc_name, lxc_obj in host.lxc.items():
                results.append((host, lxc_obj))
    return results

def find(config: YamlRoot, targets: list[str]) -> list[tuple[Host, LXC]]:
    """Find specific LXCs defined in the Yaml config by Name, IP, or VMID."""
    results = []
    if config.hosts is None:
        return results
        
    for target in targets:
        found = False
        for host in config.hosts.values():
            if host.type == "proxmox" and host.lxc is not None:
                for lxc_name, lxc_obj in host.lxc.items():
                    if (target == lxc_name or 
                        target == str(lxc_obj.ip) or 
                        target == str(lxc_obj.vmid)):
                        results.append((host, lxc_obj))
                        found = True
                        break
            if found:
                break
        if not found:
            raise KeyError(f"LXC '{target}' was not found in the configuration.")
    return results