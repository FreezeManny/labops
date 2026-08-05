from models.input_conf.yaml_root import YamlRoot
from models.input_conf.vm import VM


def findAll(config: YamlRoot) -> list[VM]:
    """Returns every VM in the Yaml config, at any nesting depth."""
    if config.hosts is None:
        raise KeyError("No hosts are defined in the configuration.")

    return [ref.node for ref in config.iter_nodes() if isinstance(ref.node, VM)]


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
