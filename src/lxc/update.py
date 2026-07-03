from src.utils.ansible_runner import run_playbook, summarize_run
from src.cli.core import report_run
from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.creds import Creds
from models.input_conf.custom_types import UNMANAGED_OS

def update(proxmox_lxc_pairs: list[tuple[Host, LXC]], default_creds: Creds, dry_run: bool = False, verbose: bool = False) -> None:
    """
    Builds a dynamic ansible inventory from the Yaml config and proxies the 
    commands via community.proxmox.proxmox_pct_remote inside community OS groups.
    """
    if not proxmox_lxc_pairs:
        print("No LXCs to update.")
        return

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
        host_user = creds.username
        
        host_vars = {
            "ansible_connection": "community.proxmox.proxmox_pct_remote",
            "ansible_host": str(host.ip),
            "ansible_user": host_user,
            "proxmox_vmid": lxc_obj.vmid,
        }
        
        if creds.ssh_key_path:
            host_vars["ansible_ssh_private_key_file"] = str(creds.ssh_key_path)
        if creds.passwd:
            host_vars["ansible_password"] = str(creds.passwd)
            
        inventory["all"]["children"][group_name]["hosts"][lxc_obj.name] = host_vars

    if not inventory["all"]["children"]:
        print("No managed LXCs to update.")
        return

    r = run_playbook(playbook="lxc/update.yml", inventory=inventory, dry_run=dry_run, verbose=verbose)
    report_run(summarize_run(r), action="LXC update")