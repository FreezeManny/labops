from typing import Optional
import typer
from rich.table import Table

from src.cli.core import get_model, resolve_targets, console
from models.input_conf.yaml_root import YamlRoot
from models.input_conf.hosts import Host
import src.host as host

app = typer.Typer(help="Manage bare-metal hosts.", no_args_is_help=True)

@app.command("setup")
def host_setup(
    target: str = typer.Argument(
        ..., help="Host name or IP address as defined in the homelab config."),
) -> None:
    """[bold]Set up[/bold] a host (initial provisioning)."""
    model: YamlRoot = get_model()
    hosts = resolve_targets(model, target, False,
                            host.find, host.findAll, label="host")
    host.setup(hosts[0], model.settings.default_creds)

@app.command("update")
def host_update(
    target: Optional[str] = typer.Argument(
        None, help="Host name or IP address."),
    all:    bool = typer.Option(False, "--all", help="Update all hosts."),
) -> None:
    """
    Run [bold]apt upgrade[/bold] on a target host or all hosts.
    [dim]Respects global --dry-run and --verbose.[/dim]
    """
    model: YamlRoot = get_model()
    hosts: list[Host] = resolve_targets(model, target, all, host.find,
                            host.findAll, label="host")
    host.update(hosts, model.settings.default_creds)

@app.command("list")
def host_list() -> None:
    """[bold]List[/bold] all hosts defined in the config."""
    model: YamlRoot = get_model()
    if not model.hosts:
        console.print("[dim]No hosts defined.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Homelab Hosts", show_header=True,
                  header_style="bold blue")
    table.add_column("Host",       style="magenta")
    table.add_column("Type",       style="cyan")
    table.add_column("OS",         style="green")
    table.add_column("IP Address", style="yellow")

    for name, h in model.hosts.items():
        table.add_row(name, str(h.type), str(h.os), str(h.ip))

    console.print(table)
