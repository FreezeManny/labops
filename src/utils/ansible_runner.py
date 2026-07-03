import os
import ansible_runner
from ansible_runner import Runner
from dataclasses import dataclass, field
from typing import Optional

project_root: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
playbook_root: str = os.path.join(project_root, "ansible", "playbooks")


@dataclass
class RunSummary:
    """Outcome of a playbook run, separating connection failures from task failures."""
    rc: int
    unreachable: dict[str, str] = field(default_factory=dict)  # host -> connection error message
    failed: list[str] = field(default_factory=list)            # hosts reached but a task failed
    ok: list[str] = field(default_factory=list)                # hosts that succeeded

    @property
    def has_unreachable(self) -> bool:
        return bool(self.unreachable)

    @property
    def succeeded(self) -> bool:
        return self.rc == 0


def summarize_run(runner: Runner) -> RunSummary:
    """
    Turn a finished Runner into a RunSummary, distinguishing hosts that could not be
    reached (Ansible 'dark' hosts) from hosts where a task failed.
    """
    stats = getattr(runner, "stats", None) or {}
    unreachable_hosts = list((stats.get("dark") or {}).keys())

    # Pull the exact connection error message per host from the event stream.
    messages: dict[str, str] = {}
    for event in getattr(runner, "events", None) or []:
        if event.get("event") != "runner_on_unreachable":
            continue
        data = event.get("event_data") or {}
        host = data.get("host")
        if host:
            messages[host] = (data.get("res") or {}).get("msg", "unreachable")

    return RunSummary(
        rc=runner.rc,
        unreachable={h: messages.get(h, "unreachable") for h in unreachable_hosts},
        failed=list((stats.get("failures") or {}).keys()),
        ok=list((stats.get("ok") or {}).keys()),
    )

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
        "envvars": {
            # Keep Python interpreter auto-discovery but suppress the warning.
            "ANSIBLE_PYTHON_INTERPRETER": "auto_silent",
            "ANSIBLE_DEPRECATION_WARNINGS": "False",
            "ANSIBLE_SYSTEM_WARNINGS": "False",
            "ANSIBLE_LOCALHOST_WARNING": "False",
            "ANSIBLE_COMMAND_WARNINGS": "False",
        },
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