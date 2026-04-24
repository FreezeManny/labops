from ansible_runner import Runner

from models.input_conf.creds import Creds
from models.docker.stack_result import StackResult
from src.utils.ansible_runner import run_playbook


def run_stacks_playbook(
    playbook: str,
    results: list[StackResult],
    default_creds: Creds,
    dry_run: bool = False,
    verbose: bool = False,
) -> Runner:
    """Run a playbook once across multiple stacks using per-host inventory variables."""
    return run_playbook(
        playbook=playbook,
        inventory=_build_multi_inventory(results, default_creds),
        dry_run=dry_run,
        verbose=verbose,
    )

def _build_multi_inventory(results: list[StackResult], default_creds: Creds) -> dict:
    """Build an inventory with one aliased entry per stack, carrying per-host vars."""
    hosts: dict = {}
    for r in results:
        creds: Creds = r.creds or default_creds
        # Use a unique alias so multiple stacks on the same host are distinct entries.
        alias = f"{r.stack.name}_{r.target_ip}"
        host_vars: dict = {
            "ansible_host": str(r.target_ip),
            "ansible_user": creds.username,
            "compose_src": str(r.stack.config_path),
            "compose_dest": f"{r.docker_root.rstrip('/')}/{r.stack.name}",
            "stack_name": r.stack.name,
        }
        if creds.passwd:
            host_vars["ansible_password"] = creds.passwd
            host_vars["ansible_become_password"] = creds.passwd
        if creds.ssh_key_path:
            host_vars["ansible_ssh_private_key_file"] = str(creds.ssh_key_path)
        hosts[alias] = host_vars
    return {"all": {"hosts": hosts}}


def _extravars(result: StackResult) -> dict:
    return {
        "compose_src": str(result.stack.config_path),
        "compose_dest": f"{result.docker_root.rstrip('/')}/{result.stack.name}",
        "stack_name": result.stack.name,
    }
