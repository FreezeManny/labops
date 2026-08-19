"""Annotated path types that resolve relative paths against the config file's
directory at validation time, then delegate to pydantic's ``FilePath`` /
``DirectoryPath`` for the existence check.

When no ``base_dir`` is supplied in the validation context (the ~80 test call
sites that build models directly), resolution falls back to ``Path.cwd()``.
"""

from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, DirectoryPath, FilePath
from pydantic import ValidationInfo


def _resolve_relative(v: object, info: ValidationInfo) -> Path:
    """Join a relative path onto ``info.context["base_dir"]``, or cwd."""
    p = Path(str(v)).expanduser()
    if p.is_absolute():
        return p
    base = (info.context or {}).get("base_dir") if info.context else None
    if base is None:
        base = Path.cwd()
    return (Path(base) / p).resolve()


ConfigRelativeFile = Annotated[FilePath, BeforeValidator(_resolve_relative)]
ConfigRelativeDir = Annotated[DirectoryPath, BeforeValidator(_resolve_relative)]
