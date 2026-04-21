from markdown_it.presets import default
from typing import Optional
import typer
from rich.table import Table

from src.cli.core import get_model, resolve_targets, console
from models.input_conf.yaml_root import YamlRoot
from models.input_conf.hosts import LXC, Host
import src.lxc as lxc

app = typer.Typer(help="Manage Proxmox LXC containers from Config.", no_args_is_help=True)

@app.command("list")
def list_lxcs() -> None:
    """List all LXCs defined in the homelab config."""
    model: YamlRoot = get_model()
    lxcs = lxc.findAll(model)
    
    if not lxcs:
        console.print("[dim]No LXC containers found in configuration.[/dim]")
        return
        
    table = Table(title="Proxmox LXCs", show_header=True,
                  header_style="bold blue")
    table.add_column("Proxmox Host", style="magenta")
    table.add_column("LXC Name",     style="cyan")
    table.add_column("VMID",         style="green")
    table.add_column("OS",           style="yellow")
    table.add_column("IP Address",   style="cyan")
    
    current_host = None
    for host, lxc_obj in lxcs:
        host_display = host.name if host.name != current_host else "╰─> "
        table.add_row(host_display, lxc_obj.name, str(lxc_obj.vmid), lxc_obj.os, str(lxc_obj.ip))
        current_host = host.name
        
    console.print(table)

@app.command("update")
def execute_update(
    target: Optional[str] = typer.Argument(
        None, help="VMID, LXC name or IP address"),
    all: bool = typer.Option(False, "--all", help="Update all LXCs."),
) -> None:
    """
    Run package upgrades natively via pct on a target LXC or all LXCs.
    """
    model: YamlRoot = get_model()
    # Resolve config targets into a list of tuples: [(Host, LXC), ...]
    targets: list[tuple[Host, LXC]] = resolve_targets(model, target, all, lxc.find,lxc.findAll, label="LXC")
    
    # Pass them directly to the Ansible builder
    lxc.update(targets, model.settings.default_creds)
