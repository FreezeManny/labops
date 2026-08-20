"""What labops publishes, and what a sync would change.

``DnsRecord`` is derived from the config (src/dns/find.py); ``LiveRecord`` is what
the DNS server currently holds, whichever server that is (src/dns/backend.py).
``DnsPlan`` is the diff between the two — computed and printed before anything is
written, because a sync has full authority over the record list and may therefore
delete.
"""

from dataclasses import dataclass
from ipaddress import IPv4Address


@dataclass(frozen=True)
class DnsRecord:
    """A single local A record derived from a config node."""

    hostname: str  # fully qualified: label + settings.dns.suffix
    ip: IPv4Address  # the node's address
    path: list[str]  # node path for diagnostics, e.g. ["cprox", "docker"]


@dataclass(frozen=True)
class LiveRecord:
    """A record as the server currently holds it, with no config counterpart."""

    hostname: str
    ip: IPv4Address


@dataclass(frozen=True)
class RecordUpdate:
    """A hostname the server already serves, but not at the address the config gives.

    ``current_ips`` is a list because a server's record list is free to hold one
    hostname twice — Pi-hole's is an array of "IP name" lines rather than a map,
    and a hosts file is no different. Publishing the config collapses those to the
    single desired address, and the plan has to be able to say so.
    """

    record: DnsRecord
    current_ips: list[IPv4Address]


@dataclass(frozen=True)
class DnsPlan:
    """Everything a sync would do to the server's record list.

    ``unchanged`` is carried so the CLI can report a total rather than only the
    delta — "19 unchanged" is what tells you the plan looked at everything.

    ``unparsed`` holds entries already on the server that labops could not read (an
    IPv6 record, a hand-mangled line). They matter to the *plan*, not just to the
    report: a sync makes the server hold exactly the config's records, so writing
    destroys them, which makes them a deletion like any other.
    """

    add: list[DnsRecord]
    update: list[RecordUpdate]
    remove: list[LiveRecord]
    unchanged: list[DnsRecord]
    unparsed: list[str]

    @property
    def has_changes(self) -> bool:
        return bool(self.add or self.update or self.remove or self.unparsed)

    @property
    def has_deletions(self) -> bool:
        """Whether applying this plan destroys anything — the case that prompts."""
        return bool(self.remove or self.unparsed)
