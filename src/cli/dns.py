from contextlib import contextmanager
from typing import Annotated, Callable, Iterator

import typer
from ansible_runner import Runner
from rich.markup import escape
from rich.table import Table

from models.dns.record import DnsPlan, DnsRecord
from models.input_conf.dns import Dns
from models.input_conf.yaml_root import YamlRoot
from src.cli.core import console, report_run, state
from src.dns import (
    PiholeError,
    apply_sync,
    dns_warnings,
    find_records,
    plan_sync,
    require_dns,
    resolve_password,
    upgrade_pihole,
)
from src.utils.ansible_runner import summarize_run

app = typer.Typer(help="Manage local DNS records on Pi-hole", no_args_is_help=True)


# ─── Shared plumbing ──────────────────────────────────────────────────────────


@contextmanager
def _clean_errors() -> Iterator[None]:
    """Turn the expected failures into a one-line message instead of a traceback.

    ``ValueError`` is a config problem (no settings.dns, no API password, an
    unresolvable upgrade target) and ``PiholeError`` is a run-time one (unreachable,
    wrong password, not v6). Both are the user's to fix, so neither deserves a stack
    trace.
    """
    try:
        yield
    except (ValueError, PiholeError) as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(1)


def _emit_warnings(model: YamlRoot) -> None:
    if state.config_path is None:
        return
    for warning in dns_warnings(model, state.config_path):
        console.print(f"[yellow]⚠ {escape(warning)}[/yellow]")


def _prepare(model: YamlRoot) -> tuple[Dns, str, list[DnsRecord]]:
    """Everything the API commands need: settings, password, desired records.

    Resolved in one place so ``sync`` does not read the secret store twice, and so
    every "you have not configured this" failure happens before the first request.
    """
    if state.config_path is None:  # unreachable via the CLI; the callback sets it
        raise ValueError("no config file is loaded.")
    dns: Dns = require_dns(model)
    password: str = resolve_password(model, state.config_path)
    return dns, password, find_records(model)


# ─── Plan rendering ───────────────────────────────────────────────────────────


def _print_plan(dns: Dns, plan: DnsPlan) -> None:
    console.print(f"\n[bold blue]Pi-hole[/bold blue] {dns.pihole_location}")

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
    """[bold]List[/bold] the local DNS records derived from the config [dim](no network)[/dim]."""
    model: YamlRoot = state.model
    with _clean_errors():
        records: list[DnsRecord] = find_records(model)

    if not records:
        console.print("[dim]No DNS records derived — every node has dns: false.[/dim]")
        raise typer.Exit(0)

    table = Table(
        title="Local DNS Records", show_header=True, header_style="bold blue"
    )
    table.add_column("Hostname", style="green")
    table.add_column("IP", style="yellow")
    table.add_column("Node", style="cyan")
    for record in records:
        table.add_row(record.hostname, str(record.ip), " → ".join(record.path))
    console.print(table)


@app.command(name="diff")
def dns_diff() -> None:
    """[bold]Compare[/bold] the config against the Pi-hole [dim](changes nothing)[/dim]."""
    model: YamlRoot = state.model
    _emit_warnings(model)
    with _clean_errors():
        dns, password, desired = _prepare(model)
        plan: DnsPlan = plan_sync(model, password, desired)

    _print_plan(dns, plan)
    if not plan.has_changes:
        console.print("\n[green]✔ Pi-hole already matches the config.[/green]")


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
    """[bold]Sync[/bold] the config's records to the Pi-hole [dim](deletes what the config no longer has)[/dim].

    [dim]The plan is always printed first; deletions ask for confirmation unless
    --yes is given. --dry-run prints the plan and stops.[/dim]
    """
    model: YamlRoot = state.model
    _emit_warnings(model)
    with _clean_errors():
        dns, password, desired = _prepare(model)
        plan: DnsPlan = plan_sync(model, password, desired)

    _print_plan(dns, plan)

    if not plan.has_changes:
        console.print("\n[green]✔ Pi-hole already matches the config.[/green]")
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
        apply_sync(model, password, desired)
    console.print(f"[green]✔ {dns.pihole_location}: {_summarize(plan)}.[/green]")


@app.command(name="upgrade")
def dns_upgrade() -> None:
    """[bold]Upgrade[/bold] the Pi-hole software itself.

    [dim]Runs Pi-hole's own updater on settings.dns.pihole_location over SSH — there
    is no API for it, and `host update` / `lxc update` only run the package manager,
    which never sees Pi-hole. Bare installs only — a containerised Pi-hole upgrades
    via `docker stack update`. --dry-run skips the command instead of running it.[/dim]
    """
    model: YamlRoot = state.model
    _run_playbook_action(
        lambda: upgrade_pihole(model, dry_run=state.dry_run, verbose=state.verbose),
        action="Pi-hole upgrade",
    )


def _run_playbook_action(run: Callable[[], Runner], action: str) -> None:
    """Run a DNS playbook and report the outcome.

    Config problems only detectable at run time — an unresolvable or ambiguous
    upgrade target, a missing upgrade block — arrive as ValueError from deep in the
    call stack, and get the same one-line treatment as everything else.
    """
    try:
        runner: Runner = run()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(1)
    report_run(summarize_run(runner), action=action)
