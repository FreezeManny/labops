"""`labops dns` — local DNS records, published to the configured DNS server.

There is no record list in the config. Every host, VM and LXC becomes
`<name>.<suffix> -> ip`, so a device that exists only to have a DNS entry is
written as an ordinary node with `os: unmanaged`. Per node, `dns_name` renames or
aliases it and `dns: false` leaves it out. The consequence is that DNS cannot
drift from the inventory: they are the same declaration.

Which server receives them is settled in src/dns/backend.py; nothing in this
module knows. Records are derived before any network access, so `dns list` works
with no server configured and no connection — useful for checking what *would* be
published. `diff` and `sync` need a server block under `settings.dns`.

`upgrade` is the odd one out. Upgrading the server software is not something every
backend can do, and where it can the mechanism is its own, so it is a dispatch
rather than part of the interface. It exists as a separate command because `host
update` / `lxc update` run the package manager, and a DNS server installed from
its own installer never appears there.
"""

from contextlib import contextmanager
from typing import Annotated, Callable, Iterator

import typer
from ansible_runner import Runner
from rich.markup import escape
from rich.table import Table

from models.dns.record import DnsPlan, DnsRecord
from models.input_conf.yaml_root import YamlRoot
from src.cli.core import console, report_run, state
from src.dns import (
    DnsBackend,
    DnsBackendError,
    dns_warnings,
    find_records,
    plan_sync,
    resolve_backend,
    upgrade_dns,
)
from src.utils.ansible_runner import summarize_run

app = typer.Typer(help="Manage local DNS records", no_args_is_help=True)


# ─── Shared plumbing ──────────────────────────────────────────────────────────


@contextmanager
def _clean_errors() -> Iterator[None]:
    """Turn the expected failures into a one-line message instead of a traceback.

    ``ValueError`` is a config problem (no settings.dns, no API password, an
    unresolvable upgrade target) and ``DnsBackendError`` is a run-time one — the
    server was unreachable, refused the password, or answered with something labops
    cannot use. Both are the user's to fix, so neither deserves a stack trace.
    """
    try:
        yield
    except (ValueError, DnsBackendError) as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(1)


def _emit_warnings(model: YamlRoot) -> None:
    if state.config_path is None:
        return
    for warning in dns_warnings(model, state.config_path):
        console.print(f"[yellow]⚠ {escape(warning)}[/yellow]")


def _prepare(model: YamlRoot) -> tuple[DnsBackend, list[DnsRecord]]:
    """The server to talk to, and the records the config wants published.

    Built in one place so a "you have not configured this" failure — no server
    block, an unresolvable location, no password — happens before the first
    request rather than halfway through a sync.
    """
    if state.config_path is None:  # unreachable via the CLI; the callback sets it
        raise ValueError("no config file is loaded.")
    backend: DnsBackend = resolve_backend(model, state.config_path)
    return backend, find_records(model)


# ─── Plan rendering ───────────────────────────────────────────────────────────


def _print_plan(backend: DnsBackend, plan: DnsPlan) -> None:
    console.print(f"\n[bold blue]{backend.name}[/bold blue] {backend.where}")

    for record in plan.add:
        console.print(f"  [green]+[/green] {record.hostname:<32} {record.ip}")
    for change in plan.update:
        was: str = ", ".join(str(ip) for ip in change.current_ips)
        console.print(
            f"  [yellow]~[/yellow] {change.record.hostname:<32} "
            f"{change.record.ip}   [dim](was {was})[/dim]"
        )
    for live in plan.remove:
        console.print(f"  [red]-[/red] {live.hostname:<32} {live.ip}")

    if plan.unchanged:
        console.print(f"  [dim]= {len(plan.unchanged)} unchanged[/dim]")
    if not plan.has_changes:
        console.print("  [dim]already up to date[/dim]")

    if plan.unparsed:
        console.print(
            f"  [yellow]⚠ {len(plan.unparsed)} existing record(s) labops cannot "
            "read; a sync would drop them:[/yellow]"
        )
        for line in plan.unparsed:
            console.print(f"    [yellow]{escape(line)}[/yellow]")


def _summarize(plan: DnsPlan) -> str:
    dropped: int = len(plan.remove) + len(plan.unparsed)
    return f"{len(plan.add)} added, {len(plan.update)} updated, {dropped} removed"


# ─── Commands ─────────────────────────────────────────────────────────────────


@app.command(name="list")
def dns_list() -> None:
    """[bold]List[/bold] the local DNS records derived from the config [dim](no network)[/dim].

    [dim]Works before you have a server to point at: records come from the
    config tree, not from the server, so this shows what `dns sync` would
    publish. Needs only settings.dns.suffix.[/dim]
    """
    model: YamlRoot = state.model
    with _clean_errors():
        records: list[DnsRecord] = find_records(model)

    if not records:
        console.print("[dim]No DNS records derived — every node has dns: false.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Local DNS Records", show_header=True, header_style="bold blue")
    table.add_column("Hostname", style="green")
    table.add_column("IP", style="yellow")
    table.add_column("Node", style="cyan")
    for record in records:
        table.add_row(record.hostname, str(record.ip), " → ".join(record.path))
    console.print(table)


@app.command(name="diff")
def dns_diff() -> None:
    """[bold]Compare[/bold] the config against the server [dim](changes nothing)[/dim].

    [dim]Shows what `dns sync` would add, change and delete. Reads the server, so
    it needs a server block under settings.dns and whatever that server
    authenticates with (for Pi-hole, PIHOLE_PASSWORD in the .env store).[/dim]
    """
    model: YamlRoot = state.model
    _emit_warnings(model)
    with _clean_errors():
        backend, desired = _prepare(model)
        plan: DnsPlan = plan_sync(backend, desired)

    _print_plan(backend, plan)
    if not plan.has_changes:
        console.print(f"\n[green]✔ {backend.name} already matches the config.[/green]")


@app.command(name="sync")
def dns_sync(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Apply without confirming, even when records will be deleted.",
        ),
    ] = False,
) -> None:
    """[bold]Sync[/bold] the config's records to the server [dim](deletes what the config no longer has)[/dim].

    [dim]The plan is always printed first; deletions ask for confirmation unless
    --yes is given. --dry-run prints the plan and stops.[/dim]
    """
    model: YamlRoot = state.model
    _emit_warnings(model)
    with _clean_errors():
        backend, desired = _prepare(model)
        plan: DnsPlan = plan_sync(backend, desired)

    _print_plan(backend, plan)

    if not plan.has_changes:
        console.print(f"\n[green]✔ {backend.name} already matches the config.[/green]")
        return

    if state.dry_run:
        console.print("\n[yellow]--dry-run: nothing was written.[/yellow]")
        return

    if plan.has_deletions and not yes:
        # Unreadable lines count here: the write replaces the whole array, so they
        # are destroyed just as surely as a record the config dropped.
        deletions: int = len(plan.remove) + len(plan.unparsed)
        console.print(
            f"\n[bold yellow]{deletions} record(s) will be deleted.[/bold yellow]"
        )
        if not typer.confirm("Continue?"):
            console.print("[dim]Aborted; nothing was written.[/dim]")
            raise typer.Exit(1)

    with _clean_errors():
        backend.apply(desired)
    console.print(f"[green]✔ {backend.where}: {_summarize(plan)}.[/green]")


@app.command(name="upgrade")
def dns_upgrade() -> None:
    """[bold]Upgrade[/bold] the DNS server software itself.

    [dim]For Pi-hole: runs its own updater on settings.dns.pihole.target over SSH —
    there is no API for it, and `host update` / `lxc update` only run the package
    manager, which never sees it. Bare installs only — a containerised Pi-hole
    upgrades via `docker stack update`. Not every backend can upgrade itself; one
    that cannot says so. --dry-run skips the command instead of running it.[/dim]
    """
    model: YamlRoot = state.model
    _run_playbook_action(
        lambda: upgrade_dns(model, dry_run=state.dry_run, verbose=state.verbose),
        action="DNS server upgrade",
    )


def _run_playbook_action(run: Callable[[], Runner], action: str) -> None:
    """Run a DNS playbook and report the outcome.

    Config problems only detectable at run time — an unresolvable or ambiguous
    upgrade target, a backend that cannot upgrade itself — arrive as ValueError
    from deep in the call stack, and get the same one-line treatment as everything
    else.
    """
    try:
        runner: Runner = run()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(1)
    report_run(summarize_run(runner), action=action)
