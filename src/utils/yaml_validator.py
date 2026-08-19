from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from models.input_conf.yaml_root import YamlRoot

console = Console()


def validate_yaml(raw: Dict[str, Any], rootPath: str) -> Optional[YamlRoot]:
    base_dir: Path = Path(rootPath).parent.resolve()

    model = None
    try:
        model: YamlRoot = YamlRoot.model_validate(
            raw, context={"base_dir": base_dir}
        )

    except ValidationError as e:
        error_messages = []
        for error in e.errors():
            # Extract the exact path of the failure (e.g., hosts.cprox)
            location: str = ".".join(str(loc) for loc in error.get("loc", []))

            # Clean up the redundant Pydantic prefix
            raw_msg: str = error.get("msg", "").replace("Value error, ", "")

            # A single validator may raise multiple newline-separated errors
            for msg in raw_msg.split("\n"):
                if location:
                    error_messages.append(
                        f"[bold yellow]{location}[/bold yellow]: [red]{msg}[/red]"
                    )
                else:
                    error_messages.append(f"[red]{msg}[/red]")

        formatted_errors = "\n".join(f"• {msg}" for msg in error_messages)

        # Print the styled error panel
        console.print(
            Panel(
                formatted_errors,
                title="[bold red]YAML Validation Failed",
                border_style="red",
                expand=False,
            )
        )

    return model
