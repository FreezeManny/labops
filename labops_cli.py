import yaml
import typer

from pathlib import Path
from typing import Callable, Optional, Annotated
from dataclasses import dataclass
from rich.console import Console
from rich.table import Table

from src.utils.yaml_validator import validate_yaml
from models.inputConf.YamlRoot import YamlRoot
from models.inputConf.hosts import Host

import src.host as host
import src.vm as vm

# ─── App ──────────────────────────────────────────────────────────────────────

app = typer.Typer(
    help="[bold cyan]LabOPS CLI[/bold cyan] — manage homelab hosts, VMs and more from a single YAML.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

console = Console()

# ─── Config discovery ─────────────────────────────────────────────────────────

# Candidate filenames searched in order, mirroring how Compose finds compose.yml
CONFIG_NAMES = ["homelab.yml", "homelab.yaml"]


def find_config(start: Path = Path.cwd()) -> Path | None:
    """Walk up the directory tree from `start` looking for a homelab config file."""
    for directory in [start, *start.parents]:
        for name in CONFIG_NAMES:
            candidate: Path = directory / name
            if candidate.is_file():
                return candidate
    return None


def resolve_config(explicit: str | None) -> Path:
    """
    Resolve the config path with two-level priority:
      1. --file / -f passed explicitly by the user
      2. Auto-discovery: walk up from cwd
    """
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            typer.secho(
                f"✘ Config file not found: {explicit}", fg=typer.colors.RED)
            raise typer.Exit(1)
        return p

    discovered: Path | None = find_config()
    if discovered:
        return discovered

    typer.secho(
        f"✘ No homelab config found.\n"
        f"  Looked for {CONFIG_NAMES} in the current directory and its parents.\n"
        f"  Use --file / -f to specify a path explicitly.",
        fg=typer.colors.RED,
    )
    raise typer.Exit(1)

# ─── Exceptions ───────────────────────────────────────────────────────────────


class ConfigError(Exception):
    """Raised when a config file cannot be loaded or fails validation."""

# ─── Shared state ─────────────────────────────────────────────────────────────


@dataclass
class AppState:
    config_path: Path | None = None
    model: YamlRoot | None = None
    dry_run: bool = False
    verbose: bool = False


state = AppState()

# ─── Shared CLI options ───────────────────────────────────────────────────────

FileOpt = Annotated[Optional[str], typer.Option(
    "--file", "-f",
    help=f"Path to homelab config file. Auto-discovered ({CONFIG_NAMES}) if omitted.",
    show_default=False,
)]

'''
DryRunOpt = Annotated[bool, typer.Option(
    "--dry-run",
    help="Preview changes without applying them (passes --check to Ansible).",
)]

VerboseOpt = Annotated[bool, typer.Option(
    "--verbose", "-v",
    help="Increase Ansible output verbosity.",
)]
'''
# ─── Loading helpers ──────────────────────────────────────────────────────────


def load_homelab_model(path: Path) -> YamlRoot:
    try:
        raw = yaml.safe_load(path.read_text())
    except Exception as e:
        raise ConfigError(f"Error reading {path}: {e}") from e

    model: YamlRoot | None = validate_yaml(raw, str(path))
    if not model:
        raise ConfigError(
            f"Validation failed for {path} — check your YAML for errors.")
    return model


def get_model() -> YamlRoot:
    """Narrow state.model YamlRoot | None → YamlRoot for commands that need it."""
    if state.model is None:
        typer.secho("✘ Config not loaded — this is a bug.",
                    fg=typer.colors.RED)
        raise typer.Exit(1)
    return state.model


def resolve_targets(
    model: YamlRoot,
    target: Optional[str],
    all_flag: bool,
    finder: Callable[[YamlRoot, list[str]], list],
    finder_all: Callable[[YamlRoot], list],
    label: str = "target",
) -> list:
    """Resolve a target name or --all into a concrete list, with friendly errors."""
    if target:
        results = finder(model, [target])
        if not results:
            typer.secho(
                f"✘ {label.capitalize()} '{target}' not found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        return results
    if all_flag:
        results = finder_all(model)
        if not results:
            typer.secho(f"✘ No {label}s found in config.", fg=typer.colors.RED)
            raise typer.Exit(1)
        return results
    typer.secho(
        f"✘ Provide a {label} name/IP, or pass --all.", fg=typer.colors.RED)
    raise typer.Exit(1)

# ─── Root callback ────────────────────────────────────────────────────────────


COMMANDS_WITHOUT_CONFIG = {"validate"}


@app.callback()
def root_callback(
    ctx:     typer.Context,
    file:    FileOpt = None,
    # dry_run: DryRunOpt = False,
    # verbose: VerboseOpt = False,
) -> None:
    """
    Global options — applied to every sub-command.
    [dim]--dry-run and --verbose are forwarded to Ansible where relevant.[/dim]
    """
    # state.dry_run = dry_run
    # state.verbose = verbose

    if ctx.invoked_subcommand in COMMANDS_WITHOUT_CONFIG:
        return

    try:
        state.config_path = resolve_config(file)
        console.print(f"[dim]Using config: {state.config_path}[/dim]")
        state.model = load_homelab_model(state.config_path)
    except ConfigError as e:
        typer.secho(f"✘ {e}", fg=typer.colors.RED)
        raise typer.Exit(1)

# ─── validate ─────────────────────────────────────────────────────────────────


@app.command()
def validate(
    file: FileOpt = None,
) -> None:
    """
    [bold]Validate[/bold] a homelab YAML — auto-discovered if not specified.
    """
    try:
        path: Path = resolve_config(file)
        console.print(f"[dim]Validating: {path}[/dim]")
        load_homelab_model(path)
        typer.secho("✔  Validation successful!", fg=typer.colors.GREEN)
    except ConfigError as e:
        typer.secho(f"✘ {e}", fg=typer.colors.RED)
        raise typer.Exit(1)

# ─── host ─────────────────────────────────────────────────────────────────────


host_app = typer.Typer(help="Manage bare-metal hosts.")
app.add_typer(host_app, name="host")


@host_app.command("setup")
def host_setup(
    target: str = typer.Argument(
        ..., help="Host name or IP address as defined in the homelab config."),
) -> None:
    """[bold]Set up[/bold] a host (initial provisioning)."""
    model = get_model()
    hosts = resolve_targets(model, target, False,
                            host.find, host.findAll, label="host")
    host.setup(hosts[0], model.settings.default_creds)


@host_app.command("update")
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


@host_app.command("list")
def host_list() -> None:
    """[bold]List[/bold] all hosts defined in the config."""
    model: YamlRoot = get_model()
    if not model.hosts:
        console.print("[dim]No hosts defined.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Homelab Hosts", show_header=True,
                  header_style="bold blue")
    table.add_column("Name",       style="cyan")
    table.add_column("Type",       style="magenta")
    table.add_column("OS",         style="green")
    table.add_column("IP Address", style="yellow")

    for name, h in model.hosts.items():
        table.add_row(name, str(h.type), str(h.os), str(h.ip))

    console.print(table)

# ─── vm ───────────────────────────────────────────────────────────────────────


vm_app = typer.Typer(help="Manage virtual machines.")
app.add_typer(vm_app, name="vm")


@vm_app.command("update")
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


@vm_app.command("list")
def vm_list() -> None:
    """[bold]List[/bold] all VMs defined in the config."""
    model: YamlRoot = get_model()
    if not model.hosts:
        console.print("[dim]No hosts defined, so no VMs.[/dim]")
        raise typer.Exit(0)

    all_vms = {}
    for h in model.hosts.values():
        if h.vm:
            all_vms.update(h.vm)

    if not all_vms:
        console.print("[dim]No VMs defined.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Homelab VMs", show_header=True,
                  header_style="bold blue")
    table.add_column("Name",       style="cyan")
    table.add_column("Type",       style="magenta")
    table.add_column("OS",         style="green")
    table.add_column("IP Address", style="yellow")

    for name, v in all_vms.items():
        table.add_row(name, str(v.type), str(v.os)+" (in VM)", str(v.ip))

    console.print(table)

# ─── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    app()


if __name__ == "__main__":
    main()
