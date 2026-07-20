from pathlib import Path
from models.input_conf.yaml_root import YamlRoot
import typer
from rich.console import Console

from src.cli.core import state, console, FileOpt, resolve_config, load_homelab_model, ConfigError
from src.cli.host import app as host_app
from src.cli.vm import app as vm_app
from src.cli.lxc import app as lxc_app
from src.cli.validate import app as validate_app
from src.cli.docker import app as docker_app
from src.cli.proxy import app as proxy_app

# ------------- APP -----------------
app = typer.Typer(
    help="[bold cyan]LabOPS CLI[/bold cyan] — manage homelab hosts, LXCs, VMs and more from a single YAML.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)


# ------------- Root Callback -----------------

COMMANDS_WITHOUT_CONFIG = set()

@app.callback()
def root_callback(
    ctx: typer.Context,
    file: FileOpt = None,
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate execution without making changes."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging in Ansible."),
) -> None:
    """
    Global options — applied to every sub-command.
    [dim]--dry-run and --verbose are forwarded to Ansible where relevant.[/dim]
    """
    state.dry_run = dry_run
    state.verbose = verbose

    if ctx.invoked_subcommand in COMMANDS_WITHOUT_CONFIG:
        return
    try:
        state.config_path = resolve_config(file)
        console.print(f"[dim]Using config: {state.config_path}[/dim]")
        state.model = load_homelab_model(state.config_path)
    except ConfigError as e:
        typer.secho(f"✘ {e}", fg=typer.colors.RED)
        raise typer.Exit(1)

# ------------- Apps -----------------
app.add_typer(validate_app, name="validate")
app.add_typer(host_app, name="host")
app.add_typer(vm_app, name="vm")
app.add_typer(lxc_app, name="lxc")
app.add_typer(docker_app, name="docker")
app.add_typer(proxy_app, name="proxy")
# ------------- Entry -----------------

def main() -> None:
    app()

if __name__ == "__main__":
    main()
