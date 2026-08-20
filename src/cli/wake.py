"""``labops wake`` — power a node on.

Two different mechanisms hide behind the one verb, and which one is right depends
on what the node *is*:

* a **bare-metal host** answers a Wake-on-LAN magic packet, sent to the ``mac`` in
  its config — from this machine, or from another node with ``--via``;
* a **Proxmox guest** does not. Nothing in a stopped VM/LXC is listening and
  Proxmox does not watch for WoL on its behalf, so it is started with ``qm start``
  / ``pct start`` on its parent node.

Picking between them automatically is the point: ``labops wake nas`` works whether
nas is a NAS on the shelf or a VM. The rule is one line — a guest is started unless
``--packet`` or ``--via`` asked for a packet — and the command always prints which
path it took, so it never has to be inferred from the outcome.

A plain command on the root app rather than a Typer sub-app, for the reason
``src/cli/update.py`` documents: a group with a positional argument parses
``labops wake nas`` as a subcommand name.
"""

from typing import Callable, Optional

import typer
from ansible_runner import Runner
from rich.markup import escape
from rich.table import Table

from models.input_conf.host import Host
from models.input_conf.yaml_root import YamlRoot
from models.nodes import node_kind
from models.nodes import NodeRef
from src.cli.core import console, report_run, state
from src.utils.ansible_runner import RunSummary, summarize_run
from src.wake import (
    DEFAULT_BROADCAST,
    DEFAULT_PORT,
    DEFAULT_WAIT_PORT,
    resolve_wake_target,
    send_magic_packet,
    send_via,
    start_guest,
    wait_until_up,
    wakeable,
)
from src.wake.run import guest_cli


def wake(
    target: Optional[str] = typer.Argument(
        None,
        metavar="[TARGET]",
        help="Host / VM / LXC name or IP.",
        show_default=False,
    ),
    via: Optional[str] = typer.Option(
        None,
        "--via",
        help="Send the magic packet from this node instead of from here. Implies --packet.",
        show_default=False,
    ),
    packet: bool = typer.Option(
        False,
        "--packet",
        help="Send a magic packet even for a VM/LXC, instead of starting it in Proxmox.",
    ),
    broadcast: str = typer.Option(
        DEFAULT_BROADCAST, "--broadcast", "-b", help="Broadcast address for the packet."
    ),
    port: int = typer.Option(
        DEFAULT_PORT, "--port", "-p", help="UDP port for the packet."
    ),
    wait: int = typer.Option(
        0,
        "--wait",
        "-w",
        help="After waking, poll for this many seconds until the node answers. 0 = don't wait.",
    ),
    wait_port: int = typer.Option(
        DEFAULT_WAIT_PORT, "--wait-port", help="TCP port polled by --wait."
    ),
    show: bool = typer.Option(
        False, "--list", help="Show every node with a mac, then exit."
    ),
) -> None:
    """
    Wake a node: a magic packet for a host, `qm`/`pct start` for a Proxmox guest.

    \b
    Examples:
      labops wake nas                  # magic packet to the nas's mac
      labops wake nas --via cprox      # broadcast it from cprox instead
      labops wake nas --wait 120       # ...and wait until it answers on :22
      labops wake pihole               # an lxc: pct start on its proxmox node
      labops wake --list               # every node that has a mac
    """
    model: YamlRoot = state.model

    if show:
        _print_wakeable(model)
        return

    if not target:
        typer.secho(
            "✘ Give a node to wake (name or IP), or pass --list.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    ref: NodeRef = _resolve(model, target)

    # The one path rule. A host has no Proxmox node above it, so it is always the
    # packet; a guest takes the packet only when asked for one.
    use_packet: bool = isinstance(ref.node, Host) or packet or via is not None

    if use_packet:
        _wake_by_packet(model, ref, via, broadcast, port)
    else:
        _start_guest(model, ref)

    if wait:
        _wait(ref, wait, wait_port)


# ─── Paths ────────────────────────────────────────────────────────────────────


def _wake_by_packet(
    model: YamlRoot, ref: NodeRef, via: Optional[str], broadcast: str, port: int
) -> None:
    where: str = " → ".join(ref.path)
    mac: Optional[str] = ref.node.mac
    if not mac:
        typer.secho(
            f"✘ '{where}' has no 'mac', so there is nothing to send a magic packet to.",
            fg=typer.colors.RED,
        )
        typer.secho(
            "  Add `mac: aa:bb:cc:dd:ee:ff` to it in the config "
            "(`labops wake --list` shows the nodes that have one).",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    # Re-bound with an explicit type: the closures below outlive the narrowing.
    mac_addr: str = mac
    origin: str = f"via {escape(via)}" if via else "from this machine"
    console.print(
        f"[bold blue]wake[/bold blue] {escape(where)} — magic packet to "
        f"[yellow]{mac_addr}[/yellow] ({broadcast}:{port}) {origin}"
    )

    if via:
        # The relay runs it, so --dry-run is ansible --check like everywhere else.
        relay: str = via
        _report(
            lambda: send_via(
                model,
                mac_addr,
                relay,
                broadcast,
                port,
                dry_run=state.dry_run,
                verbose=state.verbose,
            ),
            action="Wake-on-LAN",
        )
        return

    if state.dry_run:
        console.print("[yellow]--dry-run: no packet was sent.[/yellow]")
        return

    try:
        send_magic_packet(mac_addr, broadcast, port)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(1)
    console.print("[green]✔ Magic packet sent.[/green]")


def _start_guest(model: YamlRoot, ref: NodeRef) -> None:
    parent_name: str = ref.parent.name if ref.parent else "?"
    console.print(
        f"[bold blue]wake[/bold blue] {escape(' → '.join(ref.path))} — "
        f"{guest_cli(ref)} start on [cyan]{escape(parent_name)}[/cyan] "
        "[dim](a magic packet cannot start a Proxmox guest)[/dim]"
    )
    _report(
        lambda: start_guest(model, ref, dry_run=state.dry_run, verbose=state.verbose),
        action="Guest start",
    )


def _wait(ref: NodeRef, seconds: int, port: int) -> None:
    """Poll until the node answers, or say that it did not."""
    if state.dry_run:
        console.print("[dim]--dry-run: not waiting.[/dim]")
        return

    ip = str(ref.node.ip)
    with console.status(f"[bold]Waiting for {ip}:{port}…", spinner="dots"):
        elapsed: Optional[float] = wait_until_up(ip, port, timeout=float(seconds))

    if elapsed is None:
        console.print(
            f"[yellow]✘ {escape(ref.node.name)} did not answer on {ip}:{port} "
            f"within {seconds}s.[/yellow]"
        )
        console.print(
            "[dim]It may still be booting, or may not serve that port — "
            "try a longer --wait or a different --wait-port.[/dim]"
        )
        raise typer.Exit(1)

    console.print(
        f"[green]✔ {escape(ref.node.name)} is up ({ip}:{port}, "
        f"after {elapsed:.0f}s).[/green]"
    )


# ─── Shared plumbing ──────────────────────────────────────────────────────────


def _resolve(model: YamlRoot, target: str) -> NodeRef:
    """Same convention as ``src/cli/core.resolve_targets``: one line, no traceback."""
    try:
        return resolve_wake_target(model, target)
    except (KeyError, ValueError) as e:
        typer.secho(f"✘ {e.args[0] if e.args else e}", fg=typer.colors.RED)
        raise typer.Exit(1)


def _report(run: Callable[[], Runner], action: str) -> None:
    """Run a playbook and report it like every other labops playbook command.

    Config problems only detectable at run time — an unresolvable ``--via`` — arrive
    as ValueError from the resolver and get the same one-line treatment.
    """
    try:
        runner: Runner = run()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(1)

    summary: RunSummary = summarize_run(runner)
    report_run(summary, action=action)
    if not summary.succeeded:
        raise typer.Exit(1)


def _print_wakeable(model: YamlRoot) -> None:
    refs: list[NodeRef] = wakeable(model)
    if not refs:
        console.print(
            "[dim]No node has a 'mac'. Add one to a host to make it wakeable — "
            "VMs and LXCs are started with `labops wake <name>` regardless.[/dim]"
        )
        return

    table = Table(title="Wakeable Nodes", show_header=True, header_style="bold blue")
    table.add_column("Path", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("IP", style="yellow")
    table.add_column("MAC", style="green")

    for ref in refs:
        table.add_row(
            " → ".join(ref.path), node_kind(ref.node), str(ref.node.ip), ref.node.mac
        )
    console.print(table)
