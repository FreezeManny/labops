from typing import Optional, Sequence

from src.utils.ansible_runner import RunSummary, run_playbook, summarize_run
from src.utils.inventory import pct_host_vars
from src.cli.core import report_run
from models.input_conf.lxc import LXC
from models.input_conf.creds import Creds
from models.input_conf.custom_types import UNMANAGED_OS
from models.nodes import Parent


def update(
    proxmox_lxc_pairs: Sequence[tuple[Parent, LXC]],
    default_creds: Creds,
    dry_run: bool = False,
    verbose: bool = False,
) -> Optional[RunSummary]:
    """
    Builds a dynamic ansible inventory from the Yaml config and proxies the
    commands via community.proxmox.proxmox_pct_remote inside community OS groups.

    The pair's first element is a ``Parent`` rather than a ``Host`` because a
    container can also hang off a nested VM; either way it is only used as the
    address to proxy ``pct`` through.

    Returns the run summary, or ``None`` when there was nothing to update.
    """
    if not proxmox_lxc_pairs:
        print("No LXCs to update.")
        return None

    # Initialize the dynamic inventory with OS groups
    inventory = {"all": {"children": {}}}

    # Map the config into the Ansible structure
    for host, lxc_obj in proxmox_lxc_pairs:
        if lxc_obj.os == UNMANAGED_OS:
            print(f"Skipping unmanaged LXC: {lxc_obj.name or lxc_obj.ip}")
            continue

        group_name = f"{lxc_obj.os}_servers"
        if group_name not in inventory["all"]["children"]:
            inventory["all"]["children"][group_name] = {"hosts": {}}

        # Connect to the parent Proxmox host to proxy the execution
        creds: Creds = host.creds or default_creds
        host_vars = pct_host_vars(str(host.ip), lxc_obj.vmid, creds)

        inventory["all"]["children"][group_name]["hosts"][lxc_obj.name] = host_vars

    if not inventory["all"]["children"]:
        print("No managed LXCs to update.")
        return None

    r = run_playbook(
        playbook="lxc/update.yml", inventory=inventory, dry_run=dry_run, verbose=verbose
    )
    summary: RunSummary = summarize_run(r, kind="lxc")
    report_run(summary, action="LXC update", kind="lxc")
    return summary
