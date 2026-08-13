"""`labops proxy` — the Caddy reverse proxy, rendered from the config.

There is no route list in the config. Every `web_services` entry anywhere in the
tree that carries a `proxy_name` becomes a route, so a service is published by
declaring it on the node that runs it, next to that node's IP. One fact, one
place: move a service to another node and its route follows.

    homelab.yml  ─►  Caddyfile.j2  ─►  Caddyfile  ─►  target  ─►  caddy reload
      web_services +                    render        sync        deploy/reload
      settings.proxy

**labops owns the config file, not the Caddy instance.** The image, the DNS
provider plugin it must be built with, and the environment holding the ACME
token are managed outside labops — which is why TLS problems surface as warnings
rather than errors: labops can see the inline token and the .env store, but not
the container's own environment, where the token may perfectly well live.

The verbs split along how far they go: `render` produces the file locally,
`sync` puts it on the target, `reload` restarts Caddy against whatever is
already there, and `deploy` is sync-then-reload-if-changed. Writing your own
Caddyfile template is documented in ansible/files/proxy/README.md.
"""

from pathlib import Path
from typing import Annotated, Callable, Optional

import typer
from ansible_runner import Runner
from rich.table import Table

from src.cli.core import console, state, report_run
from models.input_conf.yaml_root import YamlRoot
from models.proxy.route_result import RouteResult
from src.proxy import (
    find_routes,
    render_caddyfile,
    tls_warnings,
    sync_proxy,
    deploy_proxy,
    reload_proxy,
)
from src.utils.ansible_runner import summarize_run

app = typer.Typer(help="Manage the Caddy reverse proxy", no_args_is_help=True)


def _emit_tls_warnings(model: YamlRoot) -> None:
    """Print any DNS-provider token sanity warnings (missing / conflicting).

    Warnings, not errors: labops only sees the inline token and the .env store,
    not the Caddy container's own environment, where the token may well live.
    """
    if state.config_path is None:
        return
    for w in tls_warnings(model, state.config_path):
        console.print(f"[yellow]⚠ {w}[/yellow]")


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
            "(set target and caddyfile_dest; add a docker: block for docker mode)."
        )
        raise typer.Exit(1)


def _run_playbook_action(run: Callable[[], Runner], action: str) -> None:
    """Run a proxy playbook and report the outcome.

    Config problems only detectable at run time — an unresolvable or ambiguous
    ``deploy.target``, a render that cannot be produced — surface as ValueError
    from deep in the call stack. They are user errors, not bugs, so they get the
    same one-line treatment as the checks above instead of a traceback.
    """
    try:
        runner: Runner = run()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    report_run(summarize_run(runner), action=action)


@app.command(name="list")
def proxy_list() -> None:
    """[bold]List[/bold] all reverse-proxy routes derived from web_services.

    [dim]One row per web_services entry that has a proxy_name; entries without
    one are tracked in the config but not routed. Shows the resolved access
    lists, so it is the quickest way to check what a service is exposed to.
    Reads the config only — Caddy is not contacted.[/dim]
    """
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
    _emit_tls_warnings(model)

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
    """[bold]Sync[/bold] the rendered Caddyfile to the Caddy host [dim](no reload)[/dim].

    [dim]The file lands on the target but Caddy keeps serving its old config
    until something reloads it — `proxy reload`, or `proxy deploy` which does
    both. Requires settings.proxy.deploy.[/dim]
    """
    model: YamlRoot = state.model
    _require_deploy_configured(model)
    _emit_tls_warnings(model)
    _run_playbook_action(
        lambda: sync_proxy(model, dry_run=state.dry_run, verbose=state.verbose),
        action="Caddyfile sync",
    )


@app.command(name="deploy")
def proxy_deploy() -> None:
    """[bold]Deploy[/bold] the Caddyfile to the Caddy host and [bold]reload[/bold] [dim](only if changed)[/dim].

    [dim]sync + reload, and the reload is skipped when the file on the target is
    already identical — so this is safe to run repeatedly. The usual command
    after editing web_services. Requires settings.proxy.deploy.[/dim]

    [dim]There is no `caddy validate` step: a Caddyfile that renders but that
    Caddy rejects lands on the target and fails at reload. Check it first with
    `proxy render`.[/dim]
    """
    model: YamlRoot = state.model
    _require_deploy_configured(model)
    _emit_tls_warnings(model)
    _run_playbook_action(
        lambda: deploy_proxy(model, dry_run=state.dry_run, verbose=state.verbose),
        action="Proxy deploy",
    )


@app.command(name="reload")
def proxy_reload() -> None:
    """[bold]Reload[/bold] Caddy on the target using its on-disk config [dim](no sync)[/dim].

    [dim]Nothing is rendered or copied — this reloads whatever Caddyfile is
    already on the target. Use it after a `sync`, or to pick up a change made on
    the target itself. Requires settings.proxy.deploy.[/dim]
    """
    model: YamlRoot = state.model
    _require_deploy_configured(model)
    _run_playbook_action(
        lambda: reload_proxy(model, dry_run=state.dry_run, verbose=state.verbose),
        action="Proxy reload",
    )
