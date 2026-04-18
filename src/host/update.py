from ansible_runner.runner import Runner
from ty_extensions import Unknown
from models.inputConf.hosts import Host
from models.inputConf.hosts import OSType
from models.inputConf.creds import Creds
from src.utils.ansible_runner import run_playbook

def update(hosts: list[Host], default_creds: Creds) -> None:
    # Group hosts by OS to run the correct playbooks
    hosts_by_os: dict[OSType, list[Host]] = {}
    for host in hosts:
        if host.os not in ["debian", "redhat", "alpine"]:
            print(f"Unsupported OS: {host.os} for host {host.ip}")
            continue
        if host.os not in hosts_by_os:
            hosts_by_os[host.os] = []
        hosts_by_os[host.os].append(host)
        
    inventory = {"all": {"children": {}}}
    
    for os_name, os_hosts in hosts_by_os.items():
        group_name = f"{os_name}_servers"
        group_hosts_dict = {}
        for host in os_hosts:
            creds: Creds = host.creds or default_creds
            host_vars: dict[str, str] = {
                "ansible_user": creds.username
            }
            if creds.passwd:
                host_vars["ansible_password"] = creds.passwd
                host_vars["ansible_become_password"] = creds.passwd
            if creds.ssh_key_path:
                host_vars["ansible_ssh_private_key_file"] = str(creds.ssh_key_path)
            
            group_hosts_dict[str(host.ip)] = host_vars
            
        inventory["all"]["children"][group_name] = {"hosts": group_hosts_dict}
        
    if not inventory["all"]["children"]:
        print("No valid hosts found to update.")
        return

    print("Running master update playbook for all hosts...")
    
    r: Runner = run_playbook(
        playbook="host/update.yml",
        inventory=inventory
    )
    
    if r.rc == 0:
        print("Ansible playbook execution completed successfully for all hosts.")
    else:
        print(f"Ansible playbook execution failed with return code {r.rc}.")
