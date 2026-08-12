"""`labops host` — the top-level nodes of the config, the `hosts:` block.

A host is anything labops reaches directly over SSH: a bare-metal box, a NAS, or
a Proxmox node (`type: proxmox`), whose guests then hang off it as `vm:` and
`lxc:`. The per-OS work — apt / apk / dnf — lives in the playbooks under
ansible/playbooks/host/, picked by the node's `os`, so the CLI stays OS-agnostic.

`os: unmanaged` marks a node labops tracks (for DNS and proxy routes) but does
not provision or patch; those are skipped here. To sweep hosts together with
guests and docker stacks in one pass, use `labops update` — see the module
docstring in src/cli/update.py for why that is a separate command.
"""

from typing import Optional
import typer
from rich.table import Table

from src.cli.core import resolve_targets, console, state
from models.input_conf.yaml_root import YamlRoot
from models.input_conf.host import Host
import src.host as host

app = typer.Typer(help="Manage bare-metal hosts.", no_args_is_help=True)


@app.command("setup")
def host_setup(
    target: str = typer.Argument(
        ..., help="Host name or IP address as defined in the homelab config."
    ),
) -> None:
    """[bold]Set up[/bold] a host (initial provisioning).

    [dim]Installs the base packages and applies the common role over SSH, using
    settings.default_creds unless the node overrides them. Run once per host;
    `host update` is what you run afterwards.[/dim]

    \b
    Examples:
      labops host setup cprox           # by name
      labops host setup 10.0.10.3       # by IP
    """
    model: YamlRoot = state.model
    hosts = resolve_targets(model, target, False, host.find, host.findAll, label="host")
    host.setup(
        hosts[0],
        model.settings.default_creds,
        dry_run=state.dry_run,
        verbose=state.verbose,
    )


@app.command("update")
def host_update(
    target: Optional[str] = typer.Argument(None, help="Host name or IP address."),
    all: bool = typer.Option(False, "--all", help="Update all hosts."),
) -> None:
    """
    Run the [bold]package manager upgrade[/bold] on a target host or all hosts.

    [dim]apt, apk or dnf, chosen by each node's os. Nodes with os: unmanaged are
    skipped. Respects global --dry-run (Ansible check mode) and --verbose.[/dim]

    \b
    Examples:
      labops host update cprox
      labops host update --all
      labops --dry-run host update --all   # check mode, changes nothing
    """
    model: YamlRoot = state.model
    hosts: list[Host] = resolve_targets(
        model, target, all, host.find, host.findAll, label="host"
    )
    host.update(
        hosts,
        model.settings.default_creds,
        dry_run=state.dry_run,
        verbose=state.verbose,
    )


@app.command("list")
def host_list() -> None:
    """[bold]List[/bold] all hosts defined in the config.

    [dim]Reads the config only — nothing is contacted, so this works offline and
    against hosts that are powered down. Guests are not shown; see `vm list` and
    `lxc list`.[/dim]
    """
    model: YamlRoot = state.model
    if not model.hosts:
        console.print("[dim]No hosts defined.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Homelab Hosts", show_header=True, header_style="bold blue")
    table.add_column("Host", style="magenta")
    table.add_column("Type", style="cyan")
    table.add_column("OS", style="green")
    table.add_column("IP Address", style="yellow")

    for name, h in model.hosts.items():
        table.add_row(name, str(h.type), str(h.os), str(h.ip))

    console.print(table)
