"""`labops lxc` — the Proxmox containers declared under a host's `lxc:` block.

Unlike hosts and VMs, an LXC is never reached over SSH. Commands run on the
Proxmox host and enter the container with `pct exec`, so a container needs no
sshd, no credentials of its own and no network route from the machine running
labops — only its `vmid` and a reachable Proxmox parent. That is also why the
unreachable-host hint here talks about the container being stopped rather than
about SSH keys (see `report_run` in src/cli/core.py).

Consequence worth knowing: software installed outside the package manager is
invisible to `lxc update`. Pi-hole is the standing example — it ships its own
installer, so it has its own `labops dns upgrade`.
"""

from typing import Optional
import typer
from rich.table import Table

from src.cli.core import resolve_targets, console, state
from models.input_conf.yaml_root import YamlRoot
from models.input_conf.host import Host
from models.input_conf.lxc import LXC
import src.lxc as lxc

app = typer.Typer(
    help="Manage Proxmox LXC containers from Config.", no_args_is_help=True
)


@app.command("list")
def list_lxcs() -> None:
    """[bold]List[/bold] all LXCs defined in the config, grouped by Proxmox host.

    [dim]Reads the config only — nothing is contacted, so this works offline and
    against containers that are stopped.[/dim]
    """
    model: YamlRoot = state.model
    lxcs = lxc.findAll(model)

    if not lxcs:
        console.print("[dim]No LXC containers found in configuration.[/dim]")
        return

    table = Table(title="Proxmox LXCs", show_header=True, header_style="bold blue")
    table.add_column("Proxmox Host", style="magenta")
    table.add_column("LXC Name", style="cyan")
    table.add_column("VMID", style="green")
    table.add_column("OS", style="yellow")
    table.add_column("IP Address", style="cyan")

    current_host = None
    for host, lxc_obj in lxcs:
        host_display = host.name if host.name != current_host else "╰─> "
        table.add_row(
            host_display, lxc_obj.name, str(lxc_obj.vmid), lxc_obj.os, str(lxc_obj.ip)
        )
        current_host = host.name

    console.print(table)


@app.command("update")
def execute_update(
    target: Optional[str] = typer.Argument(None, help="LXC name or IP address."),
    all: bool = typer.Option(False, "--all", help="Update all LXCs."),
) -> None:
    """
    Run the [bold]package manager upgrade[/bold] on a target LXC or all LXCs.

    [dim]Runs from the Proxmox host via pct — the container needs no sshd, only
    a vmid and a reachable parent. Containers with os: unmanaged are skipped, and
    software installed outside the package manager (Pi-hole) is not covered; see
    `dns upgrade`. Respects global --dry-run and --verbose.[/dim]

    \b
    Examples:
      labops lxc update pihole      # by name
      labops lxc update 10.0.0.5    # by IP
      labops lxc update --all
    """
    model: YamlRoot = state.model
    # Resolve config targets into a list of tuples: [(Host, LXC), ...]
    targets: list[tuple[Host, LXC]] = resolve_targets(
        model, target, all, lxc.find, lxc.findAll, label="LXC"
    )

    # Pass them directly to the Ansible builder
    lxc.update(
        targets,
        model.settings.default_creds,
        dry_run=state.dry_run,
        verbose=state.verbose,
    )
