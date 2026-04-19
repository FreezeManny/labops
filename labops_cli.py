from models.inputConf.hosts import Host
import yaml
import typer

from typing import Any, Annotated, Optional
from rich.console import Console
from rich.table import Table

from src.utils.yaml_validator import validate_yaml
from models.inputConf.YamlRoot import YamlRoot
from models.inputConf.creds import Creds

import src.host as host
import src.vm as vm

# ─── App & sub-apps ───────────────────────────────────────────────────────────

app = typer.Typer(
    help="[bold cyan]LabOPS CLI[/bold cyan] — manage homelab hosts, (docker stacks, DNS and proxy) from a single YAML.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

# CLI as Subcommand Structure
# Examples:
#   homelab update #To update everything
#   homelab host update <name>
#   homelab host list
#   homelab lxc update --all
#   homelab docker deploy <stack-name>

console = Console()

# ─── Shared options ───────────────────────────────────────────────────────────

DEFAULT_CONFIG = "homelab.yml"
DEFAULT_DRY_RUN = False
DEFAULT_VERBOSE = False

ConfigOpt = Annotated[str, typer.Option(
    "--config", "-c",
    help=f"Path to homelab configuration file (default: {DEFAULT_CONFIG}).",
    envvar="HOMELAB_CONFIG",
)]

DryRunOpt = Annotated[bool, typer.Option(
    "--dry-run",
    help="Preview changes without applying them (passes --check to Ansible).",
)]

VerboseOpt = Annotated[bool, typer.Option(
    "--verbose", "-v",
    help="Increase Ansible output verbosity.",
)]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_raw_yaml(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        typer.secho(f"Config file not found: {path}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        typer.secho(f"Error reading {path}: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)

def load_homelab_model(path: str) -> YamlRoot:
    raw_yaml = load_raw_yaml(path)
    model: YamlRoot | None = validate_yaml(raw_yaml, path)
    if not model:
        typer.secho("✘  Validation failed.", fg=typer.colors.RED)
        raise typer.Exit(1)
    return model

def placeholder(command: str) -> None:
    """Print a friendly 'not yet implemented' banner."""
    console.print(f"\n[bold yellow]⚙  [{command}] — not yet implemented[/bold yellow]")
    console.print("[dim]This command is a placeholder. Wire it up in the relevant module.[/dim]\n")
    raise typer.Exit(0)


# ─── validate ─────────────────────────────────────────────────────────────────

@app.command()
def validate(
    path: str = typer.Argument(..., help="Path to the YAML file to validate."),
) -> None:
    """
    [bold]Validate[/bold] a homelab YAML configuration file.
    """
    load_homelab_model(path)
    typer.secho("✔  Validation successful!", fg=typer.colors.GREEN)

# ─── host ─────────────────────────────────────────────────────────────────────

host_app = typer.Typer(help="Manage hosts.")
app.add_typer(host_app, name="host")

@host_app.command("setup")
def host_setup(
    target:     str = typer.Argument(None, help="Host name or ip-address to update as defined in homelab.yml."),
    config: ConfigOpt = DEFAULT_CONFIG,
    dry_run: DryRunOpt = DEFAULT_DRY_RUN,
    verbose: VerboseOpt = DEFAULT_VERBOSE,
) -> None:
    if target:
        inputConf: YamlRoot = load_homelab_model(config)
        hosts: Host = host.find(inputConf, [target])[0] #One Input, One Output
        if not hosts:
            typer.secho(f"✘ Host '{target}' not found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            default_creds = inputConf.settings.default_creds
            host.setup(hosts, default_creds)
    else:
        typer.secho("✘ Please provide a target hostname/IP, or use the --all flag.", fg=typer.colors.RED)
        raise typer.Exit(1)


@host_app.command("update")
def host_update(
    target:     Optional[str] = typer.Argument(None, help="Host name or ip-address to update as defined in homelab.yml."),
    all:        bool          = typer.Option(False, "--all", help="Update all hosts."),
    config:     ConfigOpt     = DEFAULT_CONFIG,
    dry_run:    DryRunOpt     = DEFAULT_DRY_RUN,
    verbose:    VerboseOpt    = DEFAULT_VERBOSE,
) -> None:
    """
    Run [bold]apt upgrade[/bold] on a target or all hosts (bare-metal, LXC, VM).
    """
    if target:
        inputConf: YamlRoot = load_homelab_model(config)
        hosts: list[Host] = host.find(inputConf, [target])
        if not hosts:
            typer.secho(f"✘ Host '{target}' not found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            default_creds: Creds = inputConf.settings.default_creds
            host.update(hosts, default_creds)
    elif all:
        inputConf: YamlRoot = load_homelab_model(config)
        hosts: list[Host] = host.findAll(inputConf)
        if not hosts:
            typer.secho(f"✘ No Host found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            default_creds: Creds = inputConf.settings.default_creds
            host.update(hosts, default_creds)
    else:
        typer.secho("✘ Please provide a target hostname/IP, or use the --all flag.", fg=typer.colors.RED)
        raise typer.Exit(1)

@host_app.command("list")
def host_list(
    config: ConfigOpt = DEFAULT_CONFIG,
) -> None:
    """
    [bold]List[/bold] all hosts defined in the configuration.
    """
    inputConf: YamlRoot = load_homelab_model(config)

    if not inputConf.hosts:
        console.print("[dim]No hosts defined.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Homelab Hosts", show_header=True, header_style="bold blue")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("OS", style="green")
    table.add_column("IP Address", style="yellow")

    for name, host in inputConf.hosts.items():
        table.add_row(name, str(host.type), str(host.os), str(host.ip))

    console.print(table)


# ─── Entry point ──────────────────────────────────────────────────────────────
vm_app = typer.Typer(help="Manage vms.")
app.add_typer(vm_app, name="vm")

@vm_app.command("update")
def vm_update(
    target:     Optional[str] = typer.Argument(None, help="VM name or ip-address to update as defined in homelab.yml."),
    all:        bool          = typer.Option(False, "--all", help="Update all VMs."),
    config:     ConfigOpt     = DEFAULT_CONFIG,
    dry_run:    DryRunOpt     = DEFAULT_DRY_RUN,
    verbose:    VerboseOpt    = DEFAULT_VERBOSE,
) -> None:
    """
    Run [bold]apt upgrade[/bold] on a target or all VMs.
    """
    if target:
        inputConf: YamlRoot = load_homelab_model(config)
        vms: list[Host] = vm.find(inputConf, [target])
        if not vms:
            typer.secho(f"✘ VM '{target}' not found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            default_creds = inputConf.settings.default_creds
            vm.update(vms, default_creds)
    elif all:
        inputConf: YamlRoot = load_homelab_model(config)
        vms: list[Host] = vm.findAll(inputConf)
        if not vms:
            typer.secho(f"✘ No VM found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            default_creds: Creds = inputConf.settings.default_creds
            vm.update(vms, default_creds)
    else:
        typer.secho("✘ Please provide a target VM/IP, or use the --all flag.", fg=typer.colors.RED)
        raise typer.Exit(1)

@vm_app.command("list")
def vm_list(
    config: ConfigOpt = DEFAULT_CONFIG,
) -> None:
    """
    [bold]List[/bold] all VMs defined in the configuration.
    """
    inputConf: YamlRoot = load_homelab_model(config)

    if not inputConf.hosts:
        console.print("[dim]No hosts defined, so no VMs.[/dim]")
        raise typer.Exit(0)

    all_vms = {}
    for h in inputConf.hosts.values():
        if h.vm:
            all_vms.update(h.vm)
            
    if not all_vms:
        console.print("[dim]No VMs defined.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Homelab VMs", show_header=True, header_style="bold blue")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("OS", style="green")
    table.add_column("IP Address", style="yellow")

    for name, v in all_vms.items():
        table.add_row(name, str(v.type), str(v.os), str(v.ip))

    console.print(table)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    app()

if __name__ == "__main__":
    main()