"""The labops secret store: a `.env`-style file holding API tokens and other
access keys, kept next to the homelab config (and out of git). labops reads it
to sanity-check that referenced secrets (e.g. the Cloudflare token) are present;
it never writes it and never renders its values unless explicitly asked to.
"""

from pathlib import Path


def resolve_env_file(config_path: Path, override: Path | None) -> Path:
    """Locate the secret store.

    ``override`` is ``settings.env_file``, already resolved to an absolute path
    by the model validator when set. When unset, defaults to a ``.env``
    alongside the config file.
    """
    if override:
        return override
    return config_path.parent / ".env"


def read_env_file(path: Path) -> dict[str, str]:
    """Parse a simple ``KEY=VALUE`` env file into a dict.

    A missing file yields ``{}`` (absence is not an error — the secret may live
    only in the deploy target's own environment). Blank lines and ``#`` comments
    are skipped, an optional ``export `` prefix is stripped, and surrounding
    single/double quotes are removed from values.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key] = val
    return values
