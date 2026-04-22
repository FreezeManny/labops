from models.input_conf.yaml_root import YamlRoot
from models.input_conf.host import Host

def findAll(config: YamlRoot) -> list[Host]:
    if config.hosts is None:
        raise KeyError("No hosts are defined in the configuration.")
    return list(config.hosts.values())

def find(config: YamlRoot, targets: list[str]) -> list[Host]:
    if config.hosts is None:
        raise KeyError("No hosts are defined in the configuration.")
        
    found_hosts: list[Host] = []
    for target in targets:
        found = False
        if target in config.hosts:
            found_hosts.append(config.hosts[target])
            found = True
        else:
            for host in config.hosts.values():
                if str(host.ip) == target:
                    found_hosts.append(host)
                    found = True
                    break
        
        if not found:
            raise KeyError(f"Host '{target}' was not found in the configuration by name or IP.")
            
    return found_hosts