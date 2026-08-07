from .diff import diff_records
from .find import find_records
from .pihole import PiholeClient, PiholeError, format_host_line, parse_hosts
from .location import PiholeLocation, resolve_location
from .sync import (
    pihole_address,
    apply_sync,
    dns_warnings,
    plan_sync,
    require_dns,
    resolve_password,
)
from .upgrade import resolve_upgrade_target, upgrade_pihole

__all__ = [
    "PiholeClient",
    "PiholeError",
    "PiholeLocation",
    "apply_sync",
    "diff_records",
    "dns_warnings",
    "find_records",
    "format_host_line",
    "parse_hosts",
    "pihole_address",
    "plan_sync",
    "require_dns",
    "resolve_upgrade_target",
    "resolve_location",
    "resolve_password",
    "upgrade_pihole",
]
