from pathlib import Path
from typing import Callable, Optional, Annotated
from dataclasses import dataclass, field
import typer
import yaml
from rich.console import Console
from src.utils.yaml_validator import validate_yaml
from src.utils.ansible_runner import RunSummary
from models.input_conf.yaml_root import YamlRoot

# ─── Shared state ─────────────────────────────────────────────────────────────

@dataclass
class AppState:
    config_path: Path | None = None
    _model: YamlRoot | None = field(default=None, init=False, repr=False)
    dry_run: bool = False
    verbose: bool = False

    @property
    def model(self) -> YamlRoot:
        assert self._model is not None
        return self._model

    @model.setter
    def model(self, value: YamlRoot) -> None:
        self._model = value

state = AppState()
console = Console()

# ─── Config discovery ─────────────────────────────────────────────────────────

CONFIG_NAMES = ["homelab.yml", "homelab.yaml"]

def find_config(start: Path = Path.cwd()) -> Path | None:
    for directory in [start, *start.parents]:
        for name in CONFIG_NAMES:
            candidate: Path = directory / name
            if candidate.is_file():
                return candidate
    return None

def resolve_config(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            typer.secho(
                f"✘ Config file not found: {explicit}", fg=typer.colors.RED)
            raise typer.Exit(1)
        return p

    discovered: Path | None = find_config()
    if discovered:
        return discovered

    typer.secho(
        f"✘ No homelab config found.\n"
        f"  Looked for {CONFIG_NAMES} in the current directory and its parents.\n"
        f"  Use --file / -f to specify a path explicitly.",
        fg=typer.colors.RED,
    )
    raise typer.Exit(1)

class ConfigError(Exception):
    """Raised when a config file cannot be loaded or fails validation."""

# ─── Run reporting ──────────────────────────────────────────────────────────

def report_run(summary: "RunSummary", action: str = "Playbook") -> None:
    """
    Print a playbook outcome, calling out unreachable hosts distinctly from
    task failures so connection problems are obvious.
    """
    if summary.succeeded:
        console.print(f"[green]✔ {action} completed successfully.[/green]")
        return

    if summary.has_unreachable:
        console.print(
            f"[bold red]✘ {len(summary.unreachable)} host(s) could not be reached:[/bold red]"
        )
        for host, msg in summary.unreachable.items():
            console.print(f"  [red]•[/red] [bold]{host}[/bold]: {msg}")
        console.print(
            "[yellow]  Check the host is powered on and that its IP, "
            "credentials/SSH key and connection are correct.[/yellow]"
        )

    if summary.failed:
        console.print(
            f"[bold red]✘ {len(summary.failed)} host(s) failed during execution:[/bold red] "
            f"{', '.join(summary.failed)}"
        )

    if not summary.has_unreachable and not summary.failed:
        console.print(f"[red]✘ {action} failed (rc={summary.rc}).[/red]")

# ─── Shared CLI options ───────────────────────────────────────────────────────

FileOpt = Annotated[Optional[str], typer.Option(
    "--file", "-f",
    help=f"Path to homelab config file. Auto-discovered ({CONFIG_NAMES}) if omitted.",
    show_default=False,
)]

def load_homelab_model(path: Path) -> YamlRoot:
    try:
        raw = yaml.safe_load(path.read_text())
    except Exception as e:
        raise ConfigError(f"Error reading {path}: {e}") from e

    model: YamlRoot | None = validate_yaml(raw, str(path))
    if not model:
        raise ConfigError(
            f"Validation failed for {path} — check your YAML for errors.")
    return model

def resolve_targets(
    model: YamlRoot,
    target: Optional[str],
    all_flag: bool,
    finder: Callable[[YamlRoot, list[str]], list],
    finder_all: Callable[[YamlRoot], list],
    label: str = "target",
) -> list:
    if target:
        results = finder(model, [target])
        if not results:
            typer.secho(
                f"✘ {label.capitalize()} '{target}' not found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        return results
    if all_flag:
        results = finder_all(model)
        if not results:
            typer.secho(f"✘ No {label}s found in config.", fg=typer.colors.RED)
            raise typer.Exit(1)
        return results
    typer.secho(
        f"✘ Provide a {label} name/IP, or pass --all.", fg=typer.colors.RED)
    raise typer.Exit(1)
