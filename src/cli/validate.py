"""`labops validate` — check the config without touching any infrastructure.

There is no separate validation pass: every command loads the config through
`load_homelab_model` in src/cli/core.py and fails the same way, so this command
is that load and nothing else. Its value is being able to run the check on its
own — in CI, in a pre-commit hook, or after an edit — rather than discovering a
typo part-way through a deploy.
"""

from typing import Optional
import typer
from pathlib import Path
from rich.table import Table

from src.cli.core import ConfigError, console, state
from models.input_conf.yaml_root import YamlRoot
from models.input_conf.host import Host

app = typer.Typer(help="Validate configuration.")


@app.callback(invoke_without_command=True)
def validate(ctx: typer.Context) -> None:
    """[bold]Validate[/bold] the homelab config and exit.

    [dim]Checks that the YAML parses, that every key is known (unknown keys are
    an error, not ignored), that values have the right type and shape — IPs,
    MACs, ports, hostnames — and that cross-field rules hold, such as a node
    name being a legal DNS label once settings.dns is configured, or credentials
    supplying exactly one auth method. Contacts nothing, so it works offline.[/dim]

    Exits 0 when the config is valid, 1 with a list of problems when it is not.

    \b
    Examples:
      labops validate                        # auto-discovered homelab.yml
      labops --file ./staging.yml validate   # a specific file
    """
    if ctx.invoked_subcommand:
        return
    model: YamlRoot = state.model
    if model:
        console.print("[bold green]✔ Configuration is valid![/bold green]")
