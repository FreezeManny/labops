from pathlib import Path
from pydantic import model_validator, field_validator, DirectoryPath
from typing import Optional, Dict

from .web_services import WebServices
from .custom_types import StrictModel


class StackEntry(StrictModel):
    name: str = ""
    config_path: DirectoryPath
    web_services: Optional[WebServices] = None

    @field_validator("config_path", mode="before")
    @classmethod
    def resolve_config_path(cls, v: object) -> Path:
        return Path(str(v)).resolve()

class Docker(StrictModel):
    root_path: str
    stacks: Dict[str, StackEntry]

    @model_validator(mode="after")
    def propagate_stack_names(self) -> "Docker":
        for k, stack in self.stacks.items():
            stack.name = k
        return self

    @model_validator(mode="after")
    def validate_unique_stack_name(self) -> "Docker":
        all_names: set[str] = set()
        for name in self.stacks.keys():
            if name in all_names:
                raise ValueError(f"Duplicate stack name: '{name}'")
            all_names.add(name)
        return self


