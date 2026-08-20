"""Local DNS: derive records from the config, diff them, publish them.

The package splits in two. Everything at this level is vendor-neutral — where
records come from (find), what a sync would change (diff, sync), where a server is
(location), and what labops needs from one (backend). Each DNS server labops can
talk to is a package below it, and ``backend.resolve_backend`` is the only place
that maps config to one of them.
"""

from .errors import DnsBackendError
from .location import (
    NodeLocation,
    ServiceLocation,
    StackLocation,
    resolve_service_location,
)
from .diff import diff_records
from .backend import DnsBackend, dns_warnings, require_dns, resolve_backend
from .find import find_records
from .sync import plan_sync
from .upgrade import upgrade_dns

__all__ = [
    "DnsBackend",
    "DnsBackendError",
    "NodeLocation",
    "ServiceLocation",
    "StackLocation",
    "diff_records",
    "dns_warnings",
    "find_records",
    "plan_sync",
    "require_dns",
    "resolve_backend",
    "resolve_service_location",
    "upgrade_dns",
]
