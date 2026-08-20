"""The annotated path types, in two families divided by *which machine* resolves
the path.

**Resolved here** — ``ConfigRelativeFile`` / ``ConfigRelativeDir``. A relative
value is joined onto the config file's directory at validation time, then handed
to pydantic's ``FilePath`` / ``DirectoryPath`` for the existence check. When no
``base_dir`` is supplied in the validation context (the ~80 test call sites that
build models directly), resolution falls back to ``Path.cwd()``.

**Resolved there** — ``RemoteAbsolutePath``. A path on a node labops deploys to,
which this machine cannot resolve, check for existence, or even reason about:
there is no base directory to join a relative value onto, so requiring an
absolute one is the whole of what can be checked here.
"""

from pathlib import Path, PurePosixPath
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


def _require_remote_absolute(v: str) -> str:
    """Reject a relative path that something else is going to resolve.

    ``PurePosixPath`` rather than ``Path``: the filesystem being described is the
    node's, so the answer must not change with the OS labops happens to run on.

    Nothing is normalised — a trailing slash is left exactly as written, because
    the one consumer that cares (``src/docker/common.py``, building ``compose_dest``)
    already strips it, and stripping it here too would be a second place to keep
    in step.
    """
    if not PurePosixPath(v).is_absolute():
        raise ValueError(f"must be an absolute path on the target (got '{v}')")
    return v


# For a path resolved on the machine labops deploys to. Applied to the field, so
# pydantic reports which one — `hosts.prox.docker.root_path` rather than a
# sentence naming the key, which is what the hand-written copies of this used to
# have to do.
RemoteAbsolutePath = Annotated[str, AfterValidator(_require_remote_absolute)]
