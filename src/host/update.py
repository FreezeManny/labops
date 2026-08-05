from ansible_runner.runner import Runner
from models.input_conf.host import Host
from models.input_conf.host import OSType
from models.input_conf.creds import Creds
from models.input_conf.custom_types import UNMANAGED_OS
from src.utils.ansible_runner import run_playbook, summarize_run
from src.utils.inventory import ssh_host_vars
from src.cli.core import report_run


def update(
    hosts: list[Host],
    default_creds: Creds,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    # Group hosts by OS to run the correct playbooks
    hosts_by_os: dict[OSType, list[Host]] = {}
    for host in hosts:
        if host.os == UNMANAGED_OS:
            print(f"Skipping unmanaged node: {host.name or host.ip}")
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
            # Keyed by IP, so no ansible_host is needed.
            group_hosts_dict[str(host.ip)] = ssh_host_vars(creds)

        inventory["all"]["children"][group_name] = {"hosts": group_hosts_dict}

    if not inventory["all"]["children"]:
        print("No valid hosts found to update.")
        return

    print("Running master update playbook for all hosts...")

    r: Runner = run_playbook(
        playbook="host/update.yml",
        inventory=inventory,
        dry_run=dry_run,
        verbose=verbose,
    )

    report_run(summarize_run(r), action="Host update")
