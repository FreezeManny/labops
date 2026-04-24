from dataclasses import dataclass, field
from typing import Optional
import typer
from rich.table import Table

from src.cli.core import get_model, console, state
from models.input_conf.creds import Creds
from src.docker import run_stacks_playbook, find, findAll
from models.docker.stack_result import StackResult

app = typer.Typer(help="Manage Docker", no_args_is_help=True)

stacks_app = typer.Typer(help="Manage Docker stacks", no_args_is_help=True)
app.add_typer(stacks_app, name="stack")

# ─── Shared stack targeting state ─────────────────────────────────────────────

@dataclass
class StackState:
    node: Optional[str] = None
    target_all: bool = False
    results: list[StackResult] = field(default_factory=list)


STACK_NAME_ARG = typer.Argument(None, help="Stack name to target.")

def _require_single(results: list[StackResult]) -> StackResult:
    """Return the single resolved stack, or exit with an error if ambiguous."""
    if len(results) > 1:
        locations = ", ".join("/".join(r.path) for r in results)
        console.print(f"[red]Ambiguous — multiple stacks matched: {locations}.[/red]")
        console.print("[dim]Use --node or provide a stack name to narrow the target.[/dim]")
        raise typer.Exit(1)
    return results[0]


def _filter_by_name(
    stack_state: StackState,
    results: list[StackResult],
    name: Optional[str],
) -> list[StackResult]:
    """Optionally narrow results to a specific stack name, erroring if none match or are ambiguous."""
    if name is None and not stack_state.target_all and stack_state.node is None:
        console.print("[red]Error:[/red] Provide a stack name, [dim]--node[/dim], or [dim]--all[/dim] to target stacks.")
        raise typer.Exit(1)
    if not name:
        return results
    filtered = [r for r in results if r.stack.name == name]
    if not filtered:
        console.print(f"[red]Error:[/red] Stack '{name}' was not found.")
        raise typer.Exit(1)
    if len(filtered) > 1 and stack_state.node is None:
        nodes = ", ".join("[magenta]" + "/".join(r.path) + "[/magenta]" for r in filtered)
        console.print(f"[red]Error:[/red] Stack '[green]{name}[/green]' exists on multiple nodes: {nodes}.")
        console.print("[dim]Use --node to specify which one.[/dim]")
        raise typer.Exit(1)
    return filtered


def _resolve_stacks(
    ctx: typer.Context,
    node: Optional[str],
    target_all: bool,
) -> StackState:
    """Return StackState using subcommand-level options when provided, else fall back to callback's state."""
    if node is not None or target_all:
        model = get_model()
        try:
            results = findAll(model) if target_all else find(model, node_name=node)
        except KeyError as e:
            console.print(f"[red]Error:[/red] {e.args[0]}")
            raise typer.Exit(1)
        if not results:
            console.print("[dim]No stacks matched.[/dim]")
            raise typer.Exit(0)
        return StackState(node=node, target_all=target_all, results=results)
    return ctx.obj


@stacks_app.callback(invoke_without_command=True)
def stacks_callback(
    ctx: typer.Context,
    node: Optional[str] = typer.Option(None, "--node", help="Match any node in the path (host, VM, or LXC name)."),
    target_all: bool = typer.Option(False, "--all", help="Target all stacks."),
) -> None:
    """
    Stack targeting options — applied to every stack sub-command.
    [dim]--node matches any name in the hierarchy (host, VM, or LXC). Use --all to target everything.[/dim]
    """
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()

    model = get_model()
    try:
        results = findAll(model) if target_all else find(model, node_name=node)
    except KeyError as e:
        console.print(f"[red]Error:[/red] {e.args[0]}")
        raise typer.Exit(1)

    if not results:
        console.print("[dim]No stacks matched.[/dim]")
        raise typer.Exit(0)

    ctx.obj = StackState(node=node, target_all=target_all, results=results)


NODE_OPT = typer.Option(None, "--node", help="Match any node in the path (host, VM, or LXC name).")
ALL_OPT = typer.Option(False, "--all", help="Target all stacks.")


@stacks_app.command(name="list")
def docker_list(
    ctx: typer.Context,
    stack_name: Optional[str] = STACK_NAME_ARG,
    node: Optional[str] = NODE_OPT,
    target_all: bool = ALL_OPT,
) -> None:
    """[bold]List[/bold] all Docker stacks defined in the homelab config."""
    stack_state = _resolve_stacks(ctx, node, target_all)
    results = _filter_by_name(stack_state, stack_state.results, stack_name)

    table = Table(title="Docker Stacks", show_header=True, header_style="bold blue")
    table.add_column("Path", style="magenta")
    table.add_column("Stack", style="green")
    table.add_column("Config Path", style="yellow")
    for r in results:
        table.add_row(" → ".join(r.path), r.stack.name, str(r.stack.config_path))
    console.print(table)

@stacks_app.command(name="deploy")
def docker_deploy(
    ctx: typer.Context,
    stack_name: Optional[str] = STACK_NAME_ARG,
    node: Optional[str] = NODE_OPT,
    target_all: bool = ALL_OPT,
) -> None:
    """[bold]Deploy[/bold] a stack by copying its config and running [dim]docker compose up -d[/dim]."""
    stack_state = _resolve_stacks(ctx, node, target_all)
    result = _require_single(_filter_by_name(stack_state, stack_state.results, stack_name))
    creds: Creds = result.creds or get_model().settings.default_creds
    runner = run_stacks_playbook("docker/deploy.yml", [result], creds, dry_run=state.dry_run, verbose=state.verbose)
    if runner.rc != 0:
        console.print(f"[red]Deploy failed (rc={runner.rc}).[/red]")
        raise typer.Exit(runner.rc or 1)
    console.print("[green]Deploy complete.[/green]")


@stacks_app.command(name="update")
def docker_update(
    ctx: typer.Context,
    stack_name: Optional[str] = STACK_NAME_ARG,
    node: Optional[str] = NODE_OPT,
    target_all: bool = ALL_OPT,
) -> None:
    """[bold]Update[/bold] a stack: pull latest images and recreate changed containers."""
    stack_state = _resolve_stacks(ctx, node, target_all)
    results = _filter_by_name(stack_state, stack_state.results, stack_name)
    default_creds: Creds = get_model().settings.default_creds
    runner = run_stacks_playbook("docker/update.yml", results, default_creds, dry_run=state.dry_run, verbose=state.verbose)
    if runner.rc != 0:
        console.print(f"[red]Update failed (rc={runner.rc}).[/red]")
        raise typer.Exit(runner.rc or 1)
    console.print("[green]All stacks updated.[/green]")

@stacks_app.command(name="sync")
def docker_sync(
    ctx: typer.Context,
    stack_name: Optional[str] = STACK_NAME_ARG,
    node: Optional[str] = NODE_OPT,
    target_all: bool = ALL_OPT,
) -> None:
    """[bold]Sync[/bold] the local [dim]config_path[/dim] files to the remote host without deploying."""
    stack_state = _resolve_stacks(ctx, node, target_all)
    result = _require_single(_filter_by_name(stack_state, stack_state.results, stack_name))
    creds: Creds = result.creds or get_model().settings.default_creds
    runner = run_stacks_playbook("docker/sync.yml", [result], creds, dry_run=state.dry_run, verbose=state.verbose)
    if runner.rc != 0:
        console.print(f"[red]Sync failed (rc={runner.rc}).[/red]")
        raise typer.Exit(runner.rc or 1)
    console.print("[green]Sync complete.[/green]")

# Future Additions: diff, validate, logs, status, restart, start, stop, down, pull