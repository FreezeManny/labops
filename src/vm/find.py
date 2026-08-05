from typing import Union

from models.input_conf.yaml_root import YamlRoot
from models.input_conf.host import Host
from models.input_conf.vm import VM


def _walk(node: Union[Host, VM], results: list[VM]) -> None:
    """Collect VMs from a node and from any VM nested under it, at any depth."""
    for vm_obj in (getattr(node, "vm", None) or {}).values():
        results.append(vm_obj)
        _walk(vm_obj, results)


def findAll(config: YamlRoot) -> list[VM]:
    """Returns every VM in the Yaml config, at any nesting depth."""
    if config.hosts is None:
        raise KeyError("No hosts are defined in the configuration.")

    vms: list[VM] = []
    for host in config.hosts.values():
        _walk(host, vms)
    return vms


def _matches(vm: VM, target: str) -> bool:
    return target in (vm.name, str(vm.ip))


def find(config: YamlRoot, targets: list[str]) -> list[VM]:
    """Find specific VMs defined in the Yaml config by Name or IP."""
    candidates: list[VM] = findAll(config)
    found_vms: list[VM] = []

    for target in targets:
        matches: list[VM] = [vm for vm in candidates if _matches(vm, target)]
        if not matches:
            raise KeyError(
                f"VM '{target}' was not found in the configuration by name or IP."
            )
        if len(matches) > 1:
            # Names are only unique per parent once VMs nest, so a name can match
            # more than one VM. Taking the first would act on the wrong machine.
            where: str = ", ".join(f"'{vm.name}' ({vm.ip})" for vm in matches)
            raise ValueError(
                f"VM '{target}' is ambiguous — it matches {len(matches)} VMs: "
                f"{where}. Target it by IP instead."
            )
        found_vms.append(matches[0])

    return found_vms
