from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.table import Table

from src.cli.core import console, state, report_run
from models.input_conf.yaml_root import YamlRoot
from models.proxy.route_result import RouteResult
from src.proxy import (
    find_routes,
    render_caddyfile,
    sync_proxy,
    deploy_proxy,
    reload_proxy,
)
from src.utils.ansible_runner import summarize_run

app = typer.Typer(help="Manage the Caddy reverse proxy", no_args_is_help=True)


def _access_label(route: RouteResult, default_list: str) -> str:
    if route.access:
        return ", ".join(route.access)
    return f"{default_list} (default)"


def _require_deploy_configured(model: YamlRoot) -> None:
    """Exit with a clear message unless settings.proxy.deploy is configured."""
    proxy = model.settings.proxy
    if proxy is None:
        console.print("[red]Error:[/red] settings.proxy is not configured.")
        raise typer.Exit(1)
    if proxy.deploy is None:
        console.print(
            "[red]Error:[/red] settings.proxy.deploy is not configured "
            "(set location, mode and caddyfile_dest to sync/deploy)."
        )
        raise typer.Exit(1)


@app.command(name="list")
def proxy_list() -> None:
    """[bold]List[/bold] all reverse-proxy routes derived from web_services."""
    model: YamlRoot = state.model
    routes: list[RouteResult] = find_routes(model)
    if not routes:
        console.print("[dim]No web_services / proxy routes defined.[/dim]")
        raise typer.Exit(0)

    proxy = model.settings.proxy
    suffix: str = proxy.proxy_suffix if proxy else ""
    default_list: str = proxy.default_access_list if proxy else ""
    table = Table(title="Proxy Routes", show_header=True, header_style="bold blue")
    table.add_column("Hostname", style="green")
    table.add_column("Upstream", style="yellow")
    table.add_column("Access", style="magenta")
    table.add_column("Path", style="cyan")
    for r in routes:
        scheme = "https://" if r.https else ""
        table.add_row(
            f"{r.proxy_name}{suffix}",
            f"{scheme}{r.target_ip}:{r.port}",
            _access_label(r, default_list),
            " → ".join(r.path),
        )
    console.print(table)


@app.command(name="render")
def proxy_render(
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Write the Caddyfile to this path instead of printing it.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite the output path if it already exists.",
        ),
    ] = False,
) -> None:
    """[bold]Render[/bold] the Caddyfile: print it, or write it to a file with [bold]-o[/bold].

    [dim]Delivery to the running Caddy is `proxy sync` / `proxy deploy`; -o is
    just for inspecting or saving a local copy.[/dim]
    """
    model: YamlRoot = state.model
    try:
        caddyfile: str = render_caddyfile(model)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if output is None:
        console.print(caddyfile, markup=False, highlight=False, soft_wrap=True)
        return

    if output.exists() and not force:
        console.print(
            f"[red]Error:[/red] {output} already exists. Pass [bold]--force[/bold] to overwrite."
        )
        raise typer.Exit(1)
    try:
        output.write_text(caddyfile)
    except OSError as e:
        console.print(f"[red]Error:[/red] could not write {output}: {e}")
        raise typer.Exit(1)
    console.print(f"[green]Caddyfile written to[/green] {output}")


@app.command(name="sync")
def proxy_sync() -> None:
    """[bold]Sync[/bold] the rendered Caddyfile to the Caddy host [dim](no reload)[/dim]."""
    model: YamlRoot = state.model
    _require_deploy_configured(model)
    r = sync_proxy(model, dry_run=state.dry_run, verbose=state.verbose)
    report_run(summarize_run(r), action="Caddyfile sync")


@app.command(name="deploy")
def proxy_deploy() -> None:
    """[bold]Deploy[/bold] the Caddyfile to the Caddy host and [bold]reload[/bold] [dim](only if changed)[/dim]."""
    model: YamlRoot = state.model
    _require_deploy_configured(model)
    r = deploy_proxy(model, dry_run=state.dry_run, verbose=state.verbose)
    report_run(summarize_run(r), action="Proxy deploy")


@app.command(name="reload")
def proxy_reload() -> None:
    """[bold]Reload[/bold] Caddy on the target using its on-disk config [dim](no sync)[/dim]."""
    model: YamlRoot = state.model
    _require_deploy_configured(model)
    r = reload_proxy(model, dry_run=state.dry_run, verbose=state.verbose)
    report_run(summarize_run(r), action="Proxy reload")
