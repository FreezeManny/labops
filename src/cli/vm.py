"""`labops vm` — the VMs declared under a Proxmox host's `vm:` block.

A VM is reached over SSH like any other node, so these commands are the host
commands pointed at a different slice of the tree; the split exists so `vm list`
can show which host a guest belongs to. Containers are `labops lxc` instead,
because those are driven through the Proxmox host with `pct` rather than SSH.

A guest with `os: unmanaged` (an appliance like HomeAssistant OS) is listed but
skipped by setup/update — there is no package manager for labops to drive. To
update VMs alongside everything else rather than on their own, use
`labops update --kind vm`; see the module docstring in src/cli/update.py.
"""

from typing import Optional
import typer
from rich.table import Table

from src.cli.core import resolve_targets, console, state
from models.input_conf.yaml_root import YamlRoot
from models.input_conf.host import Host
import src.vm as vm

app = typer.Typer(help="Manage virtual machines.", no_args_is_help=True)


@app.command("setup")
def vm_setup(
    target: str = typer.Argument(
        ..., help="VM name, IP address or vmid as defined in the homelab config."
    ),
) -> None:
    """[bold]Set up[/bold] a VM (initial provisioning).

    [dim]Installs the base packages and applies the common host role over SSH.
    Run once per guest; `vm update` is what you run afterwards.[/dim]

    \b
    Examples:
      labops vm setup fr24-radar        # by name
      labops vm setup 10.0.50.149       # by IP
    """
    model: YamlRoot = state.model
    hosts = resolve_targets(model, target, False, vm.find, vm.findAll, label="host")
    vm.setup(
        hosts[0],
        model.settings.default_creds,
        dry_run=state.dry_run,
        verbose=state.verbose,
    )


@app.command("update")
def vm_update(
    target: Optional[str] = typer.Argument(None, help="VM name, IP address or vmid."),
    all: bool = typer.Option(False, "--all", help="Update all VMs."),
) -> None:
    """
    Run the [bold]package manager upgrade[/bold] on a target VM or all VMs.

    [dim]Guests with os: unmanaged are skipped. Respects global --dry-run
    (Ansible check mode) and --verbose.[/dim]

    \b
    Examples:
      labops vm update fr24-radar
      labops vm update --all
      labops --dry-run vm update --all   # check mode, changes nothing
    """
    model: YamlRoot = state.model
    vms: list[Host] = resolve_targets(
        model, target, all, vm.find, vm.findAll, label="VM"
    )
    vm.update(
        vms, model.settings.default_creds, dry_run=state.dry_run, verbose=state.verbose
    )


@app.command("list")
def vm_list() -> None:
    """[bold]List[/bold] all VMs defined in the config, grouped by their host.

    [dim]Reads the config only — nothing is contacted, so this works offline
    and against guests that are powered down.[/dim]
    """
    model: YamlRoot = state.model
    if not model.hosts:
        console.print("[dim]No hosts defined, so no VMs.[/dim]")
        raise typer.Exit(0)

    vms_with_host = []
    for host_name, h in model.hosts.items():
        if h.vm:
            for vm_name, v in h.vm.items():
                vms_with_host.append((host_name, vm_name, v))

    if not vms_with_host:
        console.print("[dim]No VMs defined.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Homelab VMs", show_header=True, header_style="bold blue")
    table.add_column("Host", style="magenta")
    table.add_column("VM Name", style="cyan")
    table.add_column("Type", style="cyan")
    table.add_column("OS", style="green")
    table.add_column("IP Address", style="yellow")

    current_host = None
    for host_name, vm_name, v in vms_with_host:
        host_display = host_name if host_name != current_host else "╰─> "
        table.add_row(
            host_display, vm_name, str(v.type) + " (in VM)", str(v.os), str(v.ip)
        )
        current_host = host_name

    console.print(table)
