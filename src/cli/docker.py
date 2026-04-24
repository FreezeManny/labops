from dataclasses import dataclass, field
from typing import Optional
import typer
from rich.table import Table

from src.cli.core import get_model, console
from models.input_conf.yaml_root import YamlRoot
from src.docker.find import find, findAll, StackResult

app = typer.Typer(help="Manage Docker", no_args_is_help=True)

stacks_app = typer.Typer(help="Manage Docker stacks", no_args_is_help=True)
app.add_typer(stacks_app, name="stack")

# ─── Shared stack targeting state ─────────────────────────────────────────────

@dataclass
class StackState:
    node:    Optional[str]     = None
    all:     bool              = False
    results: list[StackResult] = field(default_factory=list)

stack_state = StackState()


def require_single() -> StackResult:
    """Return the single resolved stack, or exit with an error if ambiguous."""
    if len(stack_state.results) > 1:
        locations = ", ".join("/".join(r.path) for r in stack_state.results)
        console.print(f"[red]Ambiguous — multiple stacks matched: {locations}.[/red]")
        console.print("[dim]Use --node or provide a stack name to narrow the target.[/dim]")
        raise typer.Exit(1)
    return stack_state.results[0]


@stacks_app.callback(invoke_without_command=True)
def stacks_callback(
    ctx:   typer.Context,
    stack: Optional[str] = typer.Option(None, "--stack", "-s", help="Stack name to target."),
    node:  Optional[str] = typer.Option(None, "--node", help="Match any node in the path (host, VM, or LXC name)."),
    all:   bool          = typer.Option(False, "--all", help="Target all stacks."),
) -> None:
    """
    Stack targeting options — applied to every stack sub-command.
    [dim]--node matches any name in the hierarchy (host, VM, or LXC). Use --all to target everything.[/dim]
    """
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()

    stack_state.node: str | None = node
    stack_state.all: bool  = all

    model: YamlRoot = get_model()
    if all:
        results: list[StackResult] = findAll(model)
        if stack:
            results: list[StackResult] = [r for r in results if r.stack.name == stack]
    else:
        results: list[StackResult] = find(model, stack_name=stack, node_name=node)

    if not results:
        console.print("[dim]No stacks matched.[/dim]")
        raise typer.Exit(0)

    stack_state.results = results

@stacks_app.command(name="list")
def docker_list() -> None:
    """[bold]List[/bold] all Docker stacks defined in the homelab config."""
    table = Table(title="Docker Stacks", show_header=True, header_style="bold blue")
    table.add_column("Path",        style="magenta")
    table.add_column("Stack",       style="green")
    table.add_column("Config Path", style="yellow")

    for r in stack_state.results:
        table.add_row(" → ".join(r.path), r.stack.name, str(r.stack.config_path))

    console.print(table)

@stacks_app.command(name="deploy", no_args_is_help=True)
def docker_deploy() -> None:
    """[bold]Deploy[/bold] a stack by copying its config and running [dim]docker compose up -d[/dim]."""
    result: StackResult = require_single()
    console.print("[red]Not Implemented yet[/red]")

@stacks_app.command(name="update")
def docker_update() -> None:
    """[bold]Update[/bold] a stack: pull latest images and recreate changed containers."""
    console.print("[red]Not Implemented yet[/red]")

@stacks_app.command(name="sync", no_args_is_help=True)
def docker_sync() -> None:
    """[bold]Sync[/bold] the local [dim]config_path[/dim] files to the remote host without deploying."""
    result: StackResult = require_single()
    console.print("[red]Not Implemented yet[/red]")


#Future Additions: diff, validate, logs, status, restart, start, stop, down, pull