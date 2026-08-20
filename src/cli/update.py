"""``labops update`` — update an arbitrary slice of the homelab.

The per-kind commands (``host update``, ``lxc update``, ``docker stack update``)
each take one target or ``--all``. This one takes a *selector*: a set of nodes
described by kind, os, tags and position in the tree, plus the docker stacks
running on them. Selectors are also storable in the config as named target sets
(``settings.targets``), so a routine like "the debian containers I patch on
Sundays" is written once.

Execution is three sequential ansible runs — SSH nodes, then pct containers,
then stacks — because those three cannot share an inventory. See
``_run_phases`` for why.

This is a plain command on the root app rather than a Typer sub-app: a group
with a positional argument parses anything after it as a subcommand name, so
``labops update weekly --list`` would fail with "No such command '--list'".
"""

from enum import Enum
from typing import List, Optional, get_args

import typer
from rich.table import Table

from models.docker.stack_result import StackResult
from models.input_conf.custom_types import OSType
from models.input_conf.lxc import LXC
from models.input_conf.yaml_root import YamlRoot
from models.nodes import NodeKind, Selector, node_kind
from models.nodes import NodeRef
from src.cli.core import console, report_run, state
from src.utils.ansible_runner import RunSummary, summarize_run
import src.docker as docker
import src.host as host
import src.lxc as lxc

# Typer builds its --kind/--os choices from an Enum, but the values belong to the
# Selector model's Literals. Deriving the enums here means the CLI choices cannot
# drift from what the model accepts, and there is nothing to keep in sync.
KindOpt = Enum("KindOpt", {v: v for v in get_args(NodeKind)}, type=str)
OsOpt = Enum("OsOpt", {v: v for v in get_args(OSType)}, type=str)


class Only(str, Enum):
    """What a selection is used *for* — not part of the selector itself."""

    nodes = "nodes"
    stacks = "stacks"


def update(
    target_set: Optional[str] = typer.Argument(
        None,
        metavar="[SET]",
        help="A named target set from settings.targets.",
        show_default=False,
    ),
    kind: List[KindOpt] = typer.Option(
        [], "--kind", "-k", help="Node kind. Repeatable.", show_default=False
    ),
    os_: List[OsOpt] = typer.Option(
        [], "--os", help="Operating system. Repeatable.", show_default=False
    ),
    tag: List[str] = typer.Option(
        [], "--tag", "-t", help="Node tag. Repeatable.", show_default=False
    ),
    under: List[str] = typer.Option(
        [],
        "--under",
        "-u",
        help="A host/VM/LXC name: selects it and everything below it. Repeatable.",
        show_default=False,
    ),
    exclude: List[str] = typer.Option(
        [],
        "--exclude",
        "-e",
        help="A host/VM/LXC name to exclude (with its subtree). Repeatable.",
        show_default=False,
    ),
    only: Optional[Only] = typer.Option(
        None, "--only", help="Restrict to nodes or to docker stacks."
    ),
    target_all: bool = typer.Option(
        False, "--all", help="No filter — every node and stack."
    ),
    show: bool = typer.Option(
        False, "--list", help="Show what would be updated, then exit."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """
    Update the nodes a selector matches, and the docker stacks running on them.

    Selector fields combine as AND across kinds and OR within one:
    `--kind lxc --os debian` means debian containers, `--tag a --tag b` means
    tagged a or b.

    \b
    Examples:
      labops update --kind lxc --os debian    # every debian container
      labops update --under cprox             # cprox and everything below it
      labops update --tag prod --list         # preview, run nothing
      labops update weekly                    # a set from settings.targets
      labops update --all --yes               # everything, no prompt
    """
    model: YamlRoot = state.model
    selector: Selector = _resolve_selector(
        model, target_set, kind, os_, tag, under, exclude, target_all
    )

    try:
        refs: list[NodeRef] = model.select(selector)
    except KeyError as e:
        # A typo in --under. Same convention as resolve_targets: one line, no
        # traceback.
        typer.secho(f"✘ {e.args[0] if e.args else e}", fg=typer.colors.RED)
        raise typer.Exit(1)

    nodes: list[NodeRef] = [] if only is Only.stacks else refs
    stacks: list[StackResult] = (
        []
        if only is Only.nodes
        else docker.stacks_for(refs, model.settings.default_creds)
    )

    if not nodes and not stacks:
        typer.secho(
            f"✘ Nothing matched: {selector.describe()}"
            + (f" --only {only.value}" if only else ""),
            fg=typer.colors.RED,
        )
        typer.secho(
            "  Selector fields are combined with AND. "
            "Run `labops update --all --list` to see everything.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    _print_preview(nodes, stacks, selector)

    if show:
        return

    if not yes and not state.dry_run and len(nodes) + len(stacks) > 1:
        typer.confirm("Proceed?", abort=True)

    _run_phases(model, nodes, stacks)


# ─── Selector resolution ──────────────────────────────────────────────────────


def _resolve_selector(
    model: YamlRoot,
    target_set: Optional[str],
    kind: List[KindOpt],
    os_: List[OsOpt],
    tag: List[str],
    under: List[str],
    exclude: List[str],
    target_all: bool,
) -> Selector:
    """A named set or ad-hoc options — never a mix.

    Merging the two would need a rule for whether `--tag` narrows a set or
    replaces its tags; one error message is cheaper than a semantics people have
    to remember.
    """
    ad_hoc: bool = bool(kind or os_ or tag or under or exclude)

    if target_set and ad_hoc:
        typer.secho(
            "✘ Use a named set or selector options, not both.", fg=typer.colors.RED
        )
        raise typer.Exit(1)

    if target_set:
        sets = model.settings.targets
        if target_set not in sets:
            typer.secho(f"✘ No target set named '{target_set}'.", fg=typer.colors.RED)
            if sets:
                typer.secho(
                    f"  Defined sets: {', '.join(sorted(sets))}",
                    fg=typer.colors.YELLOW,
                )
            else:
                typer.secho(
                    "  No sets are defined. Add them under settings.targets, "
                    "or select with --kind/--os/--tag/--under.",
                    fg=typer.colors.YELLOW,
                )
            # The likely mistake is reaching for a node name.
            if any(target_set in ref.path for ref in model.iter_nodes()):
                typer.secho(
                    f"  '{target_set}' is a node — did you mean "
                    f"`--under {target_set}`?",
                    fg=typer.colors.YELLOW,
                )
            raise typer.Exit(1)
        return sets[target_set]

    if ad_hoc:
        return Selector(
            kind=[k.value for k in kind],
            os=[o.value for o in os_],
            tags=tag,
            under=under,
            exclude=exclude,
        )

    if target_all:
        return Selector()

    typer.secho(
        "✘ Nothing selected. Pass a selector (--kind/--os/--tag/--under), "
        "a named set, or --all.",
        fg=typer.colors.RED,
    )
    raise typer.Exit(1)


# ─── Preview ──────────────────────────────────────────────────────────────────


def _print_preview(
    nodes: list[NodeRef], stacks: list[StackResult], selector: Selector
) -> None:
    table = Table(
        title=f"Update targets — {selector.describe()}",
        show_header=True,
        header_style="bold blue",
    )
    table.add_column("Path", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("OS", style="yellow")
    table.add_column("Tags", style="green")
    table.add_column("Stacks", style="cyan")

    stacks_by_path: dict[str, list[str]] = {}
    for s in stacks:
        stacks_by_path.setdefault("/".join(s.path), []).append(s.stack.name)

    for ref in nodes:
        path = "/".join(ref.path)
        table.add_row(
            path,
            node_kind(ref.node),
            ref.node.os,
            ", ".join(ref.node.tags),
            ", ".join(stacks_by_path.pop(path, [])),
        )

    # --only stacks selects no nodes, so the stacks still need a row each.
    for path, names in stacks_by_path.items():
        table.add_row(path, "[dim]—[/dim]", "", "", ", ".join(names))

    console.print(table)

    runs: int = sum(
        1
        for bucket in (
            [r for r in nodes if not isinstance(r.node, LXC)],
            [r for r in nodes if isinstance(r.node, LXC)],
            stacks,
        )
        if bucket
    )
    suffix = " [dim](dry run — ansible --check)[/dim]" if state.dry_run else ""
    console.print(
        f"[dim]{len(nodes)} node(s), {len(stacks)} stack(s) — "
        f"{runs} ansible run(s).[/dim]{suffix}"
    )


# ─── Execution ────────────────────────────────────────────────────────────────


def _run_phases(
    model: YamlRoot, nodes: list[NodeRef], stacks: list[StackResult]
) -> None:
    """Three sequential runs: SSH nodes, pct containers, docker stacks.

    They cannot be merged into one. OS dispatch happens purely through the
    inventory group name ``{os}_servers``, and host/update.yml and lxc/update.yml
    use *the same* group names for different plays — put both in one inventory
    and the host playbook tries to SSH into containers that have no sshd. The
    connection vars differ too (pct keys by container name via the parent's IP,
    with no become password), and the docker phase is a different verb entirely.

    Ordering is packages before images, so a docker-engine upgrade lands before
    the compose run.
    """
    creds = model.settings.default_creds
    summaries: list[Optional[RunSummary]] = []

    ssh_nodes = [r.node for r in nodes if not isinstance(r.node, LXC)]
    lxc_pairs = [
        (r.parent, r.node)
        for r in nodes
        if isinstance(r.node, LXC) and r.parent is not None
    ]

    if ssh_nodes:
        _phase("Hosts & VMs")
        summaries.append(
            host.update(ssh_nodes, creds, dry_run=state.dry_run, verbose=state.verbose)
        )

    if lxc_pairs:
        _phase("Containers")
        summaries.append(
            lxc.update(lxc_pairs, creds, dry_run=state.dry_run, verbose=state.verbose)
        )

    if stacks:
        _phase("Docker stacks")
        summaries.append(_run_stacks(stacks))

    _report_total(summaries)


def _phase(name: str) -> None:
    console.print(f"\n[bold blue]── {name} ──[/bold blue]")


def _run_stacks(stacks: list[StackResult]) -> RunSummary:
    """Update stacks, reported like every other phase.

    `src/cli/docker.py` checks `runner.rc` directly, which loses the
    unreachable-vs-failed distinction and the per-host attribution. Going
    through summarize_run/report_run here keeps this command's output uniform.
    """
    runner = docker.run_stacks_playbook(
        "docker/update.yml",
        stacks,
        dry_run=state.dry_run,
        verbose=state.verbose,
    )
    summary: RunSummary = summarize_run(runner)
    report_run(summary, action="Stack update")
    return summary


def _report_total(summaries: list[Optional[RunSummary]]) -> None:
    ran = [s for s in summaries if s is not None]
    if not ran:
        console.print("\n[yellow]Nothing was run.[/yellow]")
        return

    failed = [s for s in ran if not s.succeeded]
    if failed:
        console.print(
            f"\n[bold red]✘ {len(ran) - len(failed)} of {len(ran)} "
            f"phase(s) completed.[/bold red]"
        )
        raise typer.Exit(1)

    console.print(f"\n[bold green]✔ All {len(ran)} phase(s) completed.[/bold green]")
