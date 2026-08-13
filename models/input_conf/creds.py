from pydantic import Field, model_validator, field_validator, FilePath
from typing import Optional, Dict, Any, Literal
import os
import typer

from .custom_types import StrictModel


class Creds(StrictModel):
    """SSH credentials, either as `settings.default_creds` or per node.

    Exactly one auth method must be set — a password or a key, never both and
    never neither. An ambiguous pair is a validation error rather than a silent
    preference, because which one labops picked would only become visible when a
    connection failed.
    """

    username: str = Field(..., description="The SSH user labops connects as.")
    passwd: Optional[str] = Field(
        None,
        description=(
            "Password authentication. Mutually exclusive with `ssh_key_path`. "
            "Note that some operations only work with a key, so labops warns "
            "when this is the only method available."
        ),
    )
    ssh_key_path: Optional[FilePath] = Field(
        None,
        description=(
            "Path to a private key. `~` is expanded. Mutually exclusive with "
            "`passwd`. The file must exist, so a typo fails at "
            "`labops validate` rather than at connection time."
        ),
    )

    @field_validator("ssh_key_path", mode="before")
    @classmethod
    def expand_tilde(cls, v: object) -> object:
        if isinstance(v, str) and v.startswith("~"):
            return os.path.expanduser(v)
        return v

    @model_validator(mode="after")
    def check_auth_method(self) -> "Creds":
        has_passwd = self.passwd is not None
        has_key = self.ssh_key_path is not None
        if has_passwd and has_key:
            raise ValueError(
                "Mutual exclusion error: Cannot set both passwd and ssh_key_path."
            )
        if not has_passwd and not has_key:
            raise ValueError(
                "Missing credentials: Must set either passwd or ssh_key_path."
            )
        if has_passwd and not has_key:
            typer.secho(
                "WARNING: Using only password authentication. Some features only work with an SSH key.",
                fg=typer.colors.YELLOW,
            )
        return self
