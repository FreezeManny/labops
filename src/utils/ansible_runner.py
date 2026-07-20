import os
import ansible_runner
from ansible_runner import Runner
from dataclasses import dataclass, field
from typing import Any, Optional
from rich.console import Console
from rich.markup import escape

project_root: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
playbook_root: str = os.path.join(project_root, "ansible", "playbooks")

# Own console so the event handler can print progress lines above the live
# spinner without the two fighting over the terminal.
_console = Console()

# Events whose rendered stdout we mirror to the console. Everything else
# (warnings, the verbose failure/unreachable dumps and the ansible-core error
# framework's multi-line "Origin:" source snippets) is dropped here and instead
# reported compactly — inline while running, then summarized by report_run.
_ECHO_EVENTS = frozenset(
    {
        "playbook_on_play_start",
        "playbook_on_task_start",
        "playbook_on_no_hosts_matched",  # "skipping: no hosts matched" — so empty plays aren't bare headers
        "runner_on_ok",
        "runner_on_skipped",
        "runner_item_on_ok",
        "runner_item_on_skipped",
        "playbook_on_stats",
    }
)


@dataclass
class RunSummary:
    """Outcome of a playbook run, separating connection failures from task failures."""

    rc: int
    unreachable: dict[str, str] = field(
        default_factory=dict
    )  # host -> connection error message
    failed: dict[str, str] = field(default_factory=dict)  # host -> task failure message
    ok: list[str] = field(default_factory=list)  # hosts that succeeded
    raw_tail: str = ""  # tail of raw output for un-attributed failures

    @property
    def has_unreachable(self) -> bool:
        return bool(self.unreachable)

    @property
    def succeeded(self) -> bool:
        return self.rc == 0


def _read_stdout_tail(runner: Runner, max_lines: int = 40) -> str:
    """
    Best-effort tail of the runner's raw stdout, for failures with no per-host
    attribution (syntax errors, missing playbook/inventory) that emit no events
    and would otherwise be invisible in the curated normal-mode view.
    """
    try:
        out = getattr(runner, "stdout", None)
        text = out.read() if hasattr(out, "read") else (out or "")
        lines = (text or "").strip().splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


# Signatures of an SSH/connection-level failure. Ansible sometimes reports these
# as task failures (rc 255 during temp-dir creation, or an auth rejection) rather
# than 'unreachable', even though the real cause is the host being off/unreachable
# or the credentials being wrong — all of which we want in the "unreachable" bucket
# so they get a remediation hint. NOTE: these match Ansible's English output; under
# a non-English locale detection degrades gracefully to passthrough wording.
_CONNECTION_FAILURE_SIGNS = (
    "failed to connect to the host via ssh",
    "no route to host",
    "connection refused",
    "timed out",
    "network is unreachable",
    "name or service not known",
    "failed to create temporary directory",
    "result 255",
    "permission denied",
    "unable to authenticate",
    "invalid/incorrect username/password",
)


def is_connection_failure(msg: str) -> bool:
    """True if a failure message looks like an SSH/connection problem, not a task error."""
    m = (msg or "").lower()
    return any(sign in m for sign in _CONNECTION_FAILURE_SIGNS)


def clean_failure_message(msg: str, kind: str = "host") -> str:
    """
    Boil Ansible's verbose failure text down to a short, accurate reason.
    ``kind`` tailors the wording: LXCs are driven via proxmox_pct_remote
    (SSH to the node, then ``pct exec`` in the container), so an SSH-level
    failure there means the container is stopped, not that a machine is off.
    Anything not recognised is passed through unchanged.
    """
    m = (msg or "").lower()
    # pct exec into a stopped/missing container surfaces as a temp-dir / rc 255 error.
    if kind == "lxc" and (
        "failed to create temporary directory" in m or "result 255" in m
    ):
        return "Container not reachable — is the LXC running? (pct exec failed; start it in Proxmox)"
    if "no route to host" in m or "network is unreachable" in m:
        return "No route to host — is it powered on and on the network?"
    if "connection refused" in m:
        return "Connection refused — SSH not reachable on port 22."
    if "timed out" in m:
        return "Connection timed out — host unreachable."
    if "name or service not known" in m:
        return "Host name could not be resolved."
    if (
        "permission denied" in m
        or "authentication" in m
        or "unable to authenticate" in m
        or "invalid/incorrect username/password" in m
    ):
        return "Authentication failed — check credentials/SSH key."
    if "failed to create temporary directory" in m or "result 255" in m:
        return "SSH connection failed — host may be powered off."
    return msg or "unreachable"


def summarize_run(runner: Runner, kind: str = "host") -> RunSummary:
    """
    Turn a finished Runner into a RunSummary, distinguishing hosts that could not be
    reached from hosts where a task genuinely failed. SSH-level failures that Ansible
    happened to classify as task failures are folded back into the unreachable bucket
    so the same real-world cause is always reported the same way. ``kind`` ("host"
    or "lxc") tailors the failure wording.
    """
    stats = getattr(runner, "stats", None) or {}
    dark_hosts = set((stats.get("dark") or {}).keys())
    failed_hosts = set((stats.get("failures") or {}).keys())

    # Pull the exact error message per host from the event stream (both buckets).
    messages: dict[str, str] = {}
    for event in getattr(runner, "events", None) or []:
        if event.get("event") not in ("runner_on_unreachable", "runner_on_failed"):
            continue
        data = event.get("event_data") or {}
        host = data.get("host")
        if host:
            messages[host] = (data.get("res") or {}).get("msg") or "unreachable"

    # Reclassify connection failures ('failed' but really a dead SSH / stopped
    # container) as unreachable so the same real cause reports consistently.
    reclassified = {
        h for h in failed_hosts if is_connection_failure(messages.get(h, ""))
    }
    unreachable_hosts = dark_hosts | reclassified
    failed_hosts -= reclassified

    # A non-zero rc with no per-host attribution means the failure happened before
    # or outside task execution (bad playbook path, syntax/inventory error). Those
    # emit no host events, so capture the raw tail to give report_run something to show.
    rc = runner.rc or 0
    raw_tail = (
        _read_stdout_tail(runner)
        if rc != 0 and not unreachable_hosts and not failed_hosts
        else ""
    )

    return RunSummary(
        rc=rc,
        unreachable={
            h: clean_failure_message(messages.get(h, "unreachable"), kind)
            for h in sorted(unreachable_hosts)
        },
        failed={
            h: clean_failure_message(messages.get(h, "task failed"), kind)
            for h in sorted(failed_hosts)
        },
        ok=list((stats.get("ok") or {}).keys()),
        raw_tail=raw_tail,
    )


def _clean_event_handler(event: dict) -> bool:
    """
    Mirror only the useful parts of an Ansible run to the console.

    Progress events (play/task headers, ok/skipped results, the final recap)
    are echoed verbatim; unreachable/failed hosts get a single terse line
    instead of the full JSON result and multi-line source traceback. The run
    itself is executed with ``quiet=True`` so nothing prints unless we do it
    here. Always returns True so runner keeps processing events.
    """
    etype = event.get("event")

    if etype in ("runner_on_unreachable", "runner_on_failed", "runner_item_on_failed"):
        data = event.get("event_data") or {}
        host = data.get("host", "?")
        msg = (data.get("res") or {}).get("msg", "")
        # Match summarize_run: SSH-level failures read as 'unreachable', not 'failed'.
        label = (
            "unreachable"
            if etype == "runner_on_unreachable" or is_connection_failure(msg)
            else "failed"
        )
        _console.print(f"[red]{label}: \\[{escape(host)}][/red]")
        return True

    if etype in _ECHO_EVENTS:
        stdout = event.get("stdout")
        if stdout:
            # markup/highlight off + soft_wrap so ansible's own formatting
            # (brackets, the aligned PLAY RECAP) is printed exactly as-is.
            _console.print(stdout, markup=False, highlight=False, soft_wrap=True)

    return True


def run_playbook(
    playbook: str,
    inventory: dict,
    extravars: Optional[dict] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> Runner:
    """
    Wrapper for ansible_runner.run with standard application settings.
    """
    if extravars is None:
        extravars = {}

    autogenerate_dir = os.path.join(project_root, ".ansible-autogenerate")
    os.makedirs(autogenerate_dir, exist_ok=True)

    kwargs: dict[str, Any] = {
        "private_data_dir": autogenerate_dir,
        "playbook": os.path.join(playbook_root, playbook),
        "inventory": inventory,
        "envvars": {
            # Keep Python interpreter auto-discovery but suppress the warning.
            "ANSIBLE_PYTHON_INTERPRETER": "auto_silent",
            "ANSIBLE_DEPRECATION_WARNINGS": "False",
            "ANSIBLE_SYSTEM_WARNINGS": "False",
            "ANSIBLE_LOCALHOST_WARNING": "False",
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

    # In verbose mode, let Ansible's raw stream through untouched.
    if verbose:
        return ansible_runner.run(**kwargs)

    # Normal mode: suppress Ansible's raw stream (which dumps full JSON results
    # and multi-line error tracebacks for failures) and render a clean view via
    # the event handler, with a spinner so long, quiet tasks show life.
    kwargs["quiet"] = True
    kwargs["event_handler"] = _clean_event_handler
    with _console.status("[bold]Running playbook…", spinner="dots"):
        return ansible_runner.run(**kwargs)
