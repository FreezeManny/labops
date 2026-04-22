
from pydantic import model_validator, field_validator, FilePath
from typing import Optional, Dict, Any, Literal
import os
import typer

from .custom_types import StrictModel

class Creds(StrictModel):
    username: str
    passwd: Optional[str] = None
    ssh_key_path: Optional[FilePath] = None

    @field_validator('ssh_key_path', mode='before')
    @classmethod
    def expand_tilde(cls, v: object) -> object:
        if isinstance(v, str) and v.startswith('~'):
            return os.path.expanduser(v)
        return v

    @model_validator(mode='after')
    def check_auth_method(self) -> 'Creds':
        has_passwd = self.passwd is not None
        has_key = self.ssh_key_path is not None
        if has_passwd and has_key:
            raise ValueError('Mutual exclusion error: Cannot set both passwd and ssh_key_path.')
        if not has_passwd and not has_key:
            raise ValueError('Missing credentials: Must set either passwd or ssh_key_path.')
        if has_passwd and not has_key:
            typer.secho('WARNING: Using only password authentication. Some features only work with an SSH key.', fg=typer.colors.YELLOW)
        return self