from pathlib import Path
from pydantic import Field, model_validator, field_validator, DirectoryPath
from typing import Optional, Dict

from .web_services import WebServices
from .custom_types import StrictModel


class StackEntry(StrictModel):
    """One Docker Compose stack: a local directory of compose files, plus the
    services it publishes.

    labops owns getting that directory onto the node and running compose there.
    What is inside the compose file is yours.
    """

    name: str = Field(
        "",
        description=(
            "Overrides the key this stack is written under. Leave it unset — the "
            "usual case — and the key is the name. This is the name you pass to "
            "the `docker stack` commands and the directory the stack is copied "
            "into on the node."
        ),
    )
    config_path: DirectoryPath = Field(
        ...,
        description=(
            "The local directory holding this stack's compose files, copied to "
            "the node by `docker stack sync` / `deploy`. Relative to the config "
            "file. The directory must exist, so a typo fails at "
            "`labops validate`."
        ),
    )
    web_services: Optional[WebServices] = Field(
        None,
        description=(
            "HTTP services this stack exposes. Each entry with a `proxy_name` "
            "becomes a route pointing at the node running the stack."
        ),
    )

    @field_validator("config_path", mode="before")
    @classmethod
    def resolve_config_path(cls, v: object) -> Path:
        return Path(str(v)).resolve()


class Docker(StrictModel):
    """The Docker Compose stacks running on a node."""

    root_path: str = Field(
        ...,
        description=(
            "The directory on the node that stacks are copied into; each stack "
            "lands in a subdirectory named after it."
        ),
    )
    stacks: Dict[str, StackEntry] = Field(
        ...,
        description=(
            "Stacks on this node, keyed by name. Names need not be unique across "
            "the whole config — a name matching several nodes makes the docker "
            "commands ask for `--node` rather than guess."
        ),
    )

    @model_validator(mode="after")
    def propagate_stack_names(self) -> "Docker":
        # The key names the stack unless the stack overrides it.
        for k, stack in self.stacks.items():
            if not stack.name:
                stack.name = k
        return self

    @model_validator(mode="after")
    def validate_unique_stack_name(self) -> "Docker":
        # Checked on the effective name, not the key: keys cannot collide, but
        # an override can collide with another stack's key or override, and two
        # stacks answering to one name on the same node is not addressable.
        all_names: set[str] = set()
        for stack in self.stacks.values():
            if stack.name in all_names:
                raise ValueError(f"Duplicate stack name: '{stack.name}'")
            all_names.add(stack.name)
        return self
