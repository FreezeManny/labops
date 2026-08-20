"""Where Pi-hole's API password comes from, and when to warn about it.

A password is Pi-hole's business, not DNS's: a file-based backend authenticates
with whatever reaches the file, so this sits in the backend package rather than in
the generic layer. Should a second API-based server arrive, the shape here is what
would be worth lifting out — not before.
"""

from pathlib import Path
from typing import Optional

from models.input_conf.pihole import PIHOLE_PASSWORD_ENV, Pihole
from models.input_conf.yaml_root import YamlRoot
from src.utils.env_file import read_env_file, resolve_env_file

SETTING = "settings.dns.pihole.password"


def resolve_password(config: YamlRoot, config_path: Path, pihole: Pihole) -> str:
    """The API password: inline if given, otherwise from the secret store."""
    if pihole.password:
        return pihole.password

    env_path: Path = resolve_env_file(config_path, config.settings.env_file)
    password: Optional[str] = read_env_file(env_path).get(PIHOLE_PASSWORD_ENV)
    if not password:
        raise ValueError(
            f"no Pi-hole API password found: {PIHOLE_PASSWORD_ENV} is not set in "
            f"{env_path}, and {SETTING} is unset. Pi-hole v6 accepts either the "
            "web-interface password or an application password (Settings → Web "
            "interface / API → Configure app password)."
        )
    return password


def pihole_warnings(config: YamlRoot, config_path: Path, pihole: Pihole) -> list[str]:
    """Non-fatal notes about how the API password was configured.

    Mirrors ``tls_warnings`` in src/proxy/render.py: an inline secret is legal but
    worth saying out loud, since it sits in a file that is usually committed.
    """
    if not pihole.password:
        return []
    env_path: Path = resolve_env_file(config_path, config.settings.env_file)
    return [
        f"dns: {SETTING} is set inline, in clear text in your config file. Prefer "
        f"removing it and setting {PIHOLE_PASSWORD_ENV} in {env_path}, which is "
        "git-ignored."
    ]
