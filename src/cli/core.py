from pathlib import Path
from typing import Callable, Optional, Annotated
from dataclasses import dataclass
import typer
import yaml
from rich.console import Console
from src.utils.yaml_validator import validate_yaml
from models.inputConf.YamlRoot import YamlRoot

# ─── Shared state ─────────────────────────────────────────────────────────────

@dataclass
class AppState:
    config_path: Path | None = None
    model: YamlRoot | None = None
    dry_run: bool = False
    verbose: bool = False

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

def get_model() -> YamlRoot:
    if state.model is None:
        typer.secho("✘ Config not loaded — this is a bug.",
                    fg=typer.colors.RED)
        raise typer.Exit(1)
    return state.model

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
