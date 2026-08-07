"""Planning and applying the local DNS records on the configured Pi-hole.

The plan and the apply are two separate round trips rather than one held-open
session, because a confirmation prompt sits between them and FTL sessions are
short-lived. That costs a second login and buys a session that cannot expire while
the user is reading.

Nothing about the apply depends on what was read: the desired array is derived
purely from the config, so ``apply_sync`` writes the same thing regardless of what
the Pi-hole currently holds — which is what makes a re-run after a failure safe.
"""

from pathlib import Path
from typing import Optional

from models.dns.record import DnsPlan, DnsRecord
from models.input_conf.dns import PIHOLE_PASSWORD_ENV, Dns
from models.input_conf.yaml_root import YamlRoot
from src.dns.diff import diff_records
from src.dns.pihole import PiholeClient
from src.dns.location import PiholeLocation, resolve_location
from src.utils.env_file import read_env_file, resolve_env_file


def require_dns(config: YamlRoot) -> Dns:
    """``settings.dns``, or a ValueError the CLI turns into a one-line message."""
    dns: Optional[Dns] = config.settings.dns
    if dns is None:
        raise ValueError(
            "settings.dns is not configured; set local_dns_suffix and "
            "pihole_location to manage local DNS records."
        )
    return dns


def resolve_password(config: YamlRoot, config_path: Path) -> str:
    """The Pi-hole API password: inline if given, otherwise from the secret store."""
    dns: Dns = require_dns(config)
    if dns.password:
        return dns.password

    env_path: Path = resolve_env_file(config_path, config.settings.env_file)
    password: Optional[str] = read_env_file(env_path).get(PIHOLE_PASSWORD_ENV)
    if not password:
        raise ValueError(
            f"no Pi-hole API password found: {PIHOLE_PASSWORD_ENV} is not set in "
            f"{env_path}, and settings.dns.password is unset. Pi-hole v6 accepts "
            "either the web-interface password or an application password "
            "(Settings → Web interface / API → Configure app password)."
        )
    return password


def dns_warnings(config: YamlRoot, config_path: Path) -> list[str]:
    """Non-fatal notes about where the API password came from.

    Mirrors ``tls_warnings`` in src/proxy/render.py: an inline secret is legal but
    worth saying out loud, since it sits in a file that is usually committed.
    """
    dns: Optional[Dns] = config.settings.dns
    if dns is None or not dns.password:
        return []
    env_path: Path = resolve_env_file(config_path, config.settings.env_file)
    return [
        f"dns: settings.dns.password is set inline, in clear text in your config "
        f"file. Prefer removing it and setting {PIHOLE_PASSWORD_ENV} in {env_path}, "
        "which is git-ignored."
    ]


def pihole_address(config: YamlRoot) -> str:
    """The address to call the Pi-hole API on.

    Works for all three shapes ``pihole_location`` accepts — a node, a docker stack
    (the hosting node's address) or a bare IP. See src/dns/location.py.
    """
    location: PiholeLocation = resolve_location(config, require_dns(config))
    return location.address


def _client(config: YamlRoot, password: str) -> PiholeClient:
    dns: Dns = require_dns(config)
    return PiholeClient(
        pihole_address(config),
        password,
        scheme=dns.api_scheme,
        port=dns.api_port,
    )


def plan_sync(config: YamlRoot, password: str, desired: list[DnsRecord]) -> DnsPlan:
    """Read the Pi-hole and diff it against the config. Changes nothing."""
    with _client(config, password) as client:
        current, unparsed = client.get_hosts()
    return diff_records(desired, current, unparsed)


def apply_sync(config: YamlRoot, password: str, desired: list[DnsRecord]) -> None:
    """Replace the Pi-hole's record list with exactly what the config asks for."""
    with _client(config, password) as client:
        client.set_hosts([(record.ip, record.hostname) for record in desired])
