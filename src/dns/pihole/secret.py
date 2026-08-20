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
SCHEME_SETTING = "settings.dns.pihole.scheme"


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
    """Non-fatal notes about how the API password is stored and sent.

    Mirrors ``tls_warnings`` in src/proxy/render.py: both are legal, and both put a
    secret somewhere it need not be, so they are said out loud rather than refused.

    The two are the same exposure in different places — at rest in a file that is
    usually committed, and in flight across the LAN — and the second is the one
    that used to pass unmentioned, since ``http`` was the default nobody had to
    choose.
    """
    warnings: list[str] = []

    if pihole.password:
        env_path: Path = resolve_env_file(config_path, config.settings.env_file)
        warnings.append(
            f"dns: {SETTING} is set inline, in clear text in your config file. "
            f"Prefer removing it and setting {PIHOLE_PASSWORD_ENV} in {env_path}, "
            "which is git-ignored."
        )

    if pihole.scheme == "http":
        warnings.append(
            f"dns: {SCHEME_SETTING} is http, so the API password is sent across "
            "the network in clear text. Prefer https, which Pi-hole v6 serves on "
            "443 out of the box. labops does not verify the certificate (Pi-hole's "
            "is self-signed), so this protects against eavesdropping rather than "
            "against a machine-in-the-middle."
        )

    return warnings
