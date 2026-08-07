"""What labops publishes to Pi-hole, and what a sync would change.

``DnsRecord`` is derived from the config (src/dns/find.py); ``LiveRecord`` is what
Pi-hole currently holds (src/dns/pihole.py). ``DnsPlan`` is the diff between the
two — computed and printed before anything is written, because a sync has full
authority over the record list and may therefore delete.
"""

from dataclasses import dataclass
from ipaddress import IPv4Address


@dataclass(frozen=True)
class DnsRecord:
    """A single local A record derived from a config node."""

    hostname: str  # fully qualified: label + settings.dns.local_dns_suffix
    ip: IPv4Address  # the node's address
    path: list[str]  # node path for diagnostics, e.g. ["cprox", "docker"]


@dataclass(frozen=True)
class LiveRecord:
    """A record as Pi-hole currently holds it, with no config counterpart."""

    hostname: str
    ip: IPv4Address


@dataclass(frozen=True)
class RecordUpdate:
    """A hostname Pi-hole already serves, but not at the address the config gives.

    ``current_ips`` is a list because Pi-hole's record list is free to hold one
    hostname twice (it is an array of "IP name" lines, not a map). Publishing the
    config collapses those to the single desired address, and the plan has to be
    able to say so.
    """

    record: DnsRecord
    current_ips: list[IPv4Address]


@dataclass(frozen=True)
class DnsPlan:
    """Everything a sync would do to the Pi-hole's record list.

    ``unchanged`` is carried so the CLI can report a total rather than only the
    delta — "19 unchanged" is what tells you the plan looked at everything.

    ``unparsed`` holds lines already on the Pi-hole that labops could not read (an
    IPv6 record, a hand-mangled line). They matter to the *plan*, not just to the
    report: a sync replaces the whole array, so writing destroys them, which makes
    them a deletion like any other.
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
