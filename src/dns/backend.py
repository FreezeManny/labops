"""What the DNS commands need from a DNS server, and where one is built.

``list`` derives records from the config and needs no server at all. ``diff`` and
``sync`` need exactly four things from one: a name and a location to print, the
records it currently holds, and a way to make it hold the config's instead. That is
the whole interface.

It is deliberately this narrow because a backend need not be an HTTP API. A server
whose records live in a file — written and shipped the way labops ships the
Caddyfile — has no session, no password, no port and no scheme, so none of those
appear here. Everything a particular server is peculiar about stays inside its own
package.

``apply`` takes the desired records rather than a plan of add/update/delete calls
because reaching that state is the backend's own business: Pi-hole replaces its
whole record array in one atomic PATCH, a per-record API has to work through them
one at a time, and a file backend rewrites the file. Handing over the target state
lets each do the safest thing it can.

Adding a backend: a block on ``Dns`` in models/input_conf/dns.py, a package beside
src/dns/pihole/ implementing this protocol, and a branch in ``resolve_backend``.
"""

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from models.dns.record import DnsRecord, LiveRecord
from models.input_conf.dns import Dns
from models.input_conf.yaml_root import YamlRoot
from src.dns.pihole import build_pihole_backend, pihole_warnings


@runtime_checkable
class DnsBackend(Protocol):
    """One DNS server labops can publish local records to.

    Not a context manager: whatever a server needs held open — a session, a file
    handle, an SSH connection — it holds inside ``read`` and ``apply``. The two are
    separate round trips by design, since a confirmation prompt sits between the
    plan and the apply, so there is no session for the caller to scope.
    """

    # How to name this server to the user, e.g. "Pi-hole".
    name: str

    @property
    def where(self) -> str:
        """Human-readable location, for the plan header and error messages."""
        ...

    def read(self) -> tuple[list[LiveRecord], list[str]]:
        """The records the server currently holds, plus any labops could not read.

        The second half is not a diagnostic: a sync makes the server hold exactly
        the config's records, so anything unreadable is about to be destroyed and
        the plan has to be able to say so. A backend whose records cannot be
        malformed returns an empty list.
        """
        ...

    def apply(self, desired: list[DnsRecord]) -> None:
        """Make the server hold exactly ``desired`` — no more, no fewer."""
        ...


def require_dns(config: YamlRoot) -> Dns:
    """``settings.dns``, or a ValueError the CLI turns into a one-line message."""
    dns: Optional[Dns] = config.settings.dns
    if dns is None:
        raise ValueError(
            "settings.dns is not configured; set a suffix there to derive local "
            "DNS records, and a server block to publish them."
        )
    return dns


def resolve_backend(config: YamlRoot, config_path: Path) -> DnsBackend:
    """The DNS server ``settings.dns`` points at, ready to read from.

    The one place that maps config to an implementation. Everything above it — the
    records, the diff, the plan, the CLI — works through the protocol.
    """
    dns: Dns = require_dns(config)

    # One branch per server labops speaks to.
    if dns.pihole is not None:
        return build_pihole_backend(config, config_path, dns.pihole)

    raise ValueError(
        "settings.dns names no DNS server, so labops does not know where to publish "
        "records. Add a `pihole:` block. `dns list` works without one."
    )


def dns_warnings(config: YamlRoot, config_path: Path) -> list[str]:
    """Non-fatal notes about the configured server, or none if there is none.

    Kept off the protocol because it is asked before a backend is built: the CLI
    prints these first, and building one resolves a location and may read a secret,
    either of which can fail for reasons a warning is unrelated to.
    """
    dns: Optional[Dns] = config.settings.dns
    if dns is None:
        return []
    if dns.pihole is not None:
        return pihole_warnings(config, config_path, dns.pihole)
    return []
