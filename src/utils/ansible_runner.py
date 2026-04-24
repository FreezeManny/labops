import os
import ansible_runner
from ansible_runner import Runner
from typing import Optional

project_root: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
playbook_root: str = os.path.join(project_root, "ansible", "playbooks")

def run_playbook(playbook: str, inventory: dict, extravars: Optional[dict] = None, dry_run: bool = False, verbose: bool = False) -> Runner:
    """
    Wrapper for ansible_runner.run with standard application settings.
    """
    if extravars is None:
        extravars = {}

    autogenerate_dir = os.path.join(project_root, ".ansible-autogenerate")
    os.makedirs(autogenerate_dir, exist_ok=True)

    kwargs = {
        "private_data_dir": autogenerate_dir,
        "playbook": os.path.join(playbook_root, playbook),
        "inventory": inventory,
    }

    if extravars:
        kwargs["extravars"] = extravars

    cmdline = []
    if dry_run:
        cmdline.append("--check")
    if verbose:
        cmdline.append("-v")
    
    if cmdline:
        kwargs["cmdline"] = " ".join(cmdline)
        
    runner = ansible_runner.run(**kwargs)
    return runner