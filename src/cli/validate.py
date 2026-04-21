from typing import Optional
import typer
from pathlib import Path
from rich.table import Table

from src.cli.core import ConfigError, get_model, console
from models.input_conf.yaml_root import YamlRoot
from models.input_conf.hosts import Host

app = typer.Typer(help="Validate configuration.")

@app.callback()
def validate(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand:
        return
    model: YamlRoot = get_model()
    if model:
        console.print("[bold green]✔ Configuration is valid![/bold green]")