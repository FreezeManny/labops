from ansible_runner.runner import Runner
from pathlib import Path
import getpass

from models.input_conf.host import Host
from models.input_conf.creds import Creds
from src.utils.ansible_runner import run_playbook

def setup(host: Host, default_creds: Creds, dry_run: bool = False, verbose: bool = False) -> None:
    creds: Creds = host.creds or default_creds

    if not creds.ssh_key_path:
        print("No SSH key path defined in credentials.")
        return

    # Read the public key
    pub_key_path: Path = Path(f"{creds.ssh_key_path}.pub").expanduser()
    if not pub_key_path.exists():
        print(f"SSH public key file not found: {pub_key_path}")
        return

    ssh_public_key: str = pub_key_path.read_text().strip()

    # Prompt the user interactively in the terminal for the initial user setup
    print(f"\n--- Initial Setup for {host.ip} ---")
    print(f"NOTE: Enter the existing admin user on the machine (NOT the target user '{creds.username}' which will be created).")
    initial_user: str = input(
        f"Enter initial setup username: ").strip()
    if not initial_user:
        print("Initial username cannot be blank.")
        return

    host_vars: dict[str, str] = {
        "ansible_user": initial_user,
        "ansible_ssh_common_args": "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
    }

    initial_password = ""
    use_password = input("Use password authentication for initial login? [y/N]: ").strip().lower()
    if use_password == "y":
        while not initial_password:
            initial_password = getpass.getpass(
                f"Enter SSH password for {initial_user}@{host.ip}: ")
            if not initial_password:
                print("Password cannot be blank. Please provide a password.")
        host_vars["ansible_password"] = initial_password
        host_vars["ansible_become_password"] = initial_password

    sudo_prompt = f"Enter sudo password for {initial_user}@{host.ip} (leave blank if passwordless sudo): "
    if initial_password:
        sudo_prompt = (
            f"Enter sudo password for {initial_user}@{host.ip} "
            f"(leave blank to reuse SSH password): "
        )

    sudo_password = getpass.getpass(sudo_prompt).strip()
    if sudo_password:
        host_vars["ansible_become_password"] = sudo_password

    inventory = {
        "all": {
            "children": {
                f"{host.os}_servers": {
                    "hosts": {
                        str(host.ip): host_vars
                    }
                }
            }
        }
    }

    extravars: dict[str, str] = {
        "new_username": creds.username,
        "ssh_public_key": ssh_public_key,
    }

    print(f"Running setup playbook for {host.ip}...")

    r: Runner = run_playbook(
        playbook=f"host/setup.yml",
        inventory=inventory,
        extravars=extravars,
        dry_run=dry_run,
        verbose=verbose
    )

    if r.rc == 0:
        print("Ansible setup playbook execution completed successfully.")
    else:
        print(f"Ansible playbook execution failed with return code {r.rc}.")
