from typing import Optional
import typer
from rich.table import Table

from src.cli.core import get_model, resolve_targets, console
from models.input_conf.yaml_root import YamlRoot
from models.input_conf.hosts import Host
import src.vm as vm

app = typer.Typer(help="Manage virtual machines.", no_args_is_help=True)

@app.command("setup")
def host_setup(
    target: str = typer.Argument(
        ..., help="Host name or IP address as defined in the homelab config."),
) -> None:
    """[bold]Set up[/bold] a host (initial provisioning)."""
    model: YamlRoot = get_model()
    hosts = resolve_targets(model, target, False,
                            vm.find,vm.findAll, label="host")
    vm.setup(hosts[0], model.settings.default_creds)

@app.command("update")
def vm_update(
    target: Optional[str] = typer.Argument(
        None, help="VM name or IP address."),
    all:    bool = typer.Option(False, "--all", help="Update all VMs."),
) -> None:
    """
    Run [bold]apt upgrade[/bold] on a target VM or all VMs.
    [dim]Respects global --dry-run and --verbose.[/dim]
    """
    model: YamlRoot = get_model()
    vms: list[Host] = resolve_targets(model, target, all, vm.find, vm.findAll, label="VM")
    vm.update(vms, model.settings.default_creds)

@app.command("list")
def vm_list() -> None:
    """[bold]List[/bold] all VMs defined in the config."""
    model: YamlRoot = get_model()
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

    table = Table(title="Homelab VMs", show_header=True,
                  header_style="bold blue")
    table.add_column("Host",       style="magenta")
    table.add_column("VM Name",    style="cyan")
    table.add_column("Type",       style="cyan")
    table.add_column("OS",         style="green")
    table.add_column("IP Address", style="yellow")

    current_host = None
    for host_name, vm_name, v in vms_with_host:
        host_display = host_name if host_name != current_host else "╰─> "
        table.add_row(host_display, vm_name, str(v.type) + " (in VM)", str(v.os), str(v.ip))
        current_host = host_name

    console.print(table)
