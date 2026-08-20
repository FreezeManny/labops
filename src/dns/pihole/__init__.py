"""Pi-hole v6 as a labops DNS backend.

Everything specific to Pi-hole lives in here: the REST session, the ``dns.hosts``
text format, the API password, which config block says where it is, and its own
updater. The generic layer above (src/dns/backend.py) knows only the four members
of ``DnsBackend``.
"""

from .client import PiholeClient, PiholeError
from .location import SETTING, resolve_pihole_location
from .secret import pihole_warnings, resolve_password
from .upgrade import resolve_upgrade_target, upgrade_pihole
from .wire import format_host_line, parse_hosts
from .backend import PiholeBackend, build_pihole_backend

__all__ = [
    "PiholeBackend",
    "PiholeClient",
    "PiholeError",
    "SETTING",
    "build_pihole_backend",
    "format_host_line",
    "parse_hosts",
    "pihole_warnings",
    "resolve_password",
    "resolve_pihole_location",
    "resolve_upgrade_target",
    "upgrade_pihole",
]
