import typer
from rich.table import Table
from ansible_runner import Runner

from src.cli.core import console, state
from models.input_conf.yaml_root import YamlRoot
from models.proxy.route_result import RouteResult
from src.proxy import find_routes, render_caddyfile, sync_proxy, deploy_proxy

app = typer.Typer(help="Manage the Caddy reverse proxy", no_args_is_help=True)


def _access_label(route: RouteResult, default_list: str) -> str:
    if route.access:
        return ", ".join(route.access)
    return f"{default_list} (default)"


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
        table.add_row(f"{r.proxy_name}{suffix}", f"{r.target_ip}:{r.port}", _access_label(r, default_list), " → ".join(r.path))
    console.print(table)

@app.command(name="render")
def proxy_render() -> None:
    """[bold]Render[/bold] the Caddyfile locally and print it [dim](no deploy)[/dim]."""
    model: YamlRoot = state.model
    try:
        caddyfile: str = render_caddyfile(model)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(caddyfile, markup=False, highlight=False, soft_wrap=True)


@app.command(name="sync")
def proxy_sync() -> None:
    """[bold]Sync[/bold] the rendered Caddyfile to the proxy host [dim](no reload)[/dim]."""
    model: YamlRoot = state.model
    try:
        runner: Runner = sync_proxy(model, dry_run=state.dry_run, verbose=state.verbose)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if runner.rc != 0:
        console.print(f"[red]Proxy sync failed (rc={runner.rc}).[/red]")
        raise typer.Exit(runner.rc or 1)
    console.print("[green]Proxy sync complete.[/green]")


@app.command(name="deploy")
def proxy_deploy() -> None:
    """[bold]Deploy[/bold]: write the Caddyfile to [dim]proxy_location[/dim] and reload Caddy."""
    model: YamlRoot = state.model
    try:
        runner: Runner = deploy_proxy(model, dry_run=state.dry_run, verbose=state.verbose)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if runner.rc != 0:
        console.print(f"[red]Proxy deploy failed (rc={runner.rc}).[/red]")
        raise typer.Exit(runner.rc or 1)
    console.print("[green]Proxy deploy complete.[/green]")
