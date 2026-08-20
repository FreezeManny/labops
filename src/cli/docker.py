"""`labops docker stack` — the compose stacks declared under a node's `docker:`
block.

A stack is a directory of compose files on your machine (`config_path`) plus the
node that should run it. labops owns getting that directory onto the node and
running compose there; it does not own the compose file's contents.

The three verbs differ only in how far they go:

    sync    copy config_path to the node                (nothing runs)
    deploy  sync, then `docker compose up -d`           (start it)
    update  pull newer images, recreate what changed    (patch it)

`update` is the one that takes many stacks at once, because patching everything
is a routine sweep; `deploy` and `sync` require a single unambiguous target,
since pushing files to the wrong node is not something to do in bulk. Stack names
need not be unique across the config, so a name matching several nodes is an
error asking for `--node` rather than a guess.

`labops update` runs the stacks on the nodes it matches, so a full sweep does not
need this command at all — see the module docstring in src/cli/update.py.
"""

from ansible_runner.runner import Runner
from models.input_conf.yaml_root import YamlRoot
from dataclasses import dataclass, field
from typing import Optional
import typer
from rich.table import Table

from src.cli.core import console, state
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


def _filter_by_name(
    stack_state: StackState,
    results: list[StackResult],
    name: Optional[str],
    require_single: bool = False,
) -> list[StackResult]:
    """Filter results by stack name, erroring if none match or are ambiguous."""
    if name is None and not stack_state.target_all and stack_state.node is None:
        console.print(
            "[red]Error:[/red] Provide a stack name, [dim]--node[/dim], or [dim]--all[/dim] to target stacks."
        )
        raise typer.Exit(1)
    if name:
        filtered: list[StackResult] = [r for r in results if r.stack.name == name]
        if not filtered:
            console.print(f"[red]Error:[/red] Stack '{name}' was not found.")
            raise typer.Exit(1)
        if len(filtered) > 1 and stack_state.node is None:
            nodes: str = ", ".join(
                "[magenta]" + "/".join(r.path) + "[/magenta]" for r in filtered
            )
            console.print(
                f"[red]Error:[/red] Stack '[green]{name}[/green]' exists on multiple nodes: {nodes}."
            )
            console.print("[dim]Use --node to specify which one.[/dim]")
            raise typer.Exit(1)
        results = filtered
    if require_single and len(results) > 1:
        locations: str = ", ".join("/".join(r.path) for r in results)
        console.print(f"[red]Ambiguous — multiple stacks matched: {locations}.[/red]")
        console.print(
            "[dim]Use --node or provide a stack name to narrow the target.[/dim]"
        )
        raise typer.Exit(1)
    return results


def _resolve_stacks(
    ctx: typer.Context,
    node: Optional[str],
    target_all: bool,
) -> StackState:
    """Return StackState using subcommand-level options when provided, else fall back to callback's state."""
    if node is not None or target_all:
        model: YamlRoot = state.model
        try:
            results: list[StackResult] = (
                findAll(model) if target_all else find(model, node_name=node)
            )
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
    node: Optional[str] = typer.Option(
        None, "--node", help="Match any node in the path (host, VM, or LXC name)."
    ),
    target_all: bool = typer.Option(False, "--all", help="Target all stacks."),
) -> None:
    """
    Stack targeting options — applied to every stack sub-command.
    [dim]--node matches any name in the hierarchy (host, VM, or LXC). Use --all to target everything.[/dim]
    """
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()

    model: YamlRoot = state.model
    try:
        results: list[StackResult] = (
            findAll(model) if target_all else find(model, node_name=node)
        )
    except KeyError as e:
        console.print(f"[red]Error:[/red] {e.args[0]}")
        raise typer.Exit(1)

    if not results:
        console.print("[dim]No stacks matched.[/dim]")
        raise typer.Exit(0)

    ctx.obj = StackState(node=node, target_all=target_all, results=results)


NODE_OPT = typer.Option(
    None, "--node", help="Match any node in the path (host, VM, or LXC name)."
)
ALL_OPT = typer.Option(False, "--all", help="Target all stacks.")


@stacks_app.command(name="list")
def docker_list(
    ctx: typer.Context,
    stack_name: Optional[str] = STACK_NAME_ARG,
    node: Optional[str] = NODE_OPT,
    target_all: bool = ALL_OPT,
) -> None:
    """[bold]List[/bold] all Docker stacks defined in the config, with the node
    each one runs on.

    [dim]Reads the config only — nothing is contacted, so this does not show
    whether a stack is actually running.[/dim]

    \b
    Examples:
      labops docker stack list --all
      labops docker stack list --node home
    """
    stack_state: StackState = _resolve_stacks(ctx, node, target_all)
    results: list[StackResult] = _filter_by_name(
        stack_state, stack_state.results, stack_name
    )

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
    """[bold]Deploy[/bold] a stack: copy its config to the node, then [dim]docker compose up -d[/dim].

    [dim]One stack at a time — pass a name, or --node if the name is not unique.
    Use `sync` to copy the files without starting anything, and `update` to pull
    newer images for a stack that is already running.[/dim]

    \b
    Examples:
      labops docker stack deploy homeassistant
      labops docker stack deploy nginx-proxy-manager --node docker
    """
    stack_state: StackState = _resolve_stacks(ctx, node, target_all)
    result: StackResult = _filter_by_name(
        stack_state, stack_state.results, stack_name, require_single=True
    )[0]
    runner: Runner = run_stacks_playbook(
        "docker/deploy.yml",
        [result],
        dry_run=state.dry_run,
        verbose=state.verbose,
    )
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
    """[bold]Update[/bold] stacks: pull the latest images and recreate changed containers.

    [dim]Unlike deploy/sync this accepts many stacks at once, so --all or --node
    sweeps them. Config files are not re-copied; run `sync` or `deploy` when the
    compose file itself changed.[/dim]

    \b
    Examples:
      labops docker stack update --all
      labops docker stack update --node home
      labops docker stack update homeassistant
    """
    stack_state: StackState = _resolve_stacks(ctx, node, target_all)
    results: list[StackResult] = _filter_by_name(
        stack_state, stack_state.results, stack_name
    )
    runner: Runner = run_stacks_playbook(
        "docker/update.yml",
        results,
        dry_run=state.dry_run,
        verbose=state.verbose,
    )
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
    """[bold]Sync[/bold] a stack's local [dim]config_path[/dim] files to its node, without deploying.

    [dim]Nothing is started or restarted, so the running containers keep their
    current config until you `deploy`. One stack at a time — pass a name, or
    --node if the name is not unique.[/dim]

    \b
    Examples:
      labops docker stack sync caddy
      labops docker stack sync nginx-proxy-manager --node docker
    """
    stack_state: StackState = _resolve_stacks(ctx, node, target_all)
    result: StackResult = _filter_by_name(
        stack_state, stack_state.results, stack_name, require_single=True
    )[0]
    runner: Runner = run_stacks_playbook(
        "docker/sync.yml",
        [result],
        dry_run=state.dry_run,
        verbose=state.verbose,
    )
    if runner.rc != 0:
        console.print(f"[red]Sync failed (rc={runner.rc}).[/red]")
        raise typer.Exit(runner.rc or 1)
    console.print("[green]Sync complete.[/green]")


# Future Additions: diff, validate, logs, status, restart, start, stop, down, pull
