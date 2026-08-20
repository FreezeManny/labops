"""Pi-hole as a DnsBackend: the four things the DNS commands ask of a server.

Everything peculiar to Pi-hole is reached from here and nowhere else — the session
(client.py), the ``dns.hosts`` text format (wire.py), the API password
(secret.py) and which config block said where it is (location.py).

Each of ``read`` and ``apply`` opens and closes its own session rather than the
caller holding one: FTL has a small fixed number of session slots and a
confirmation prompt sits between the plan and the apply, so a held-open session
would be an expiring one.
"""

from ipaddress import IPv4Address
from pathlib import Path

from models.dns.record import DnsRecord, LiveRecord
from models.input_conf.pihole import Pihole
from models.input_conf.yaml_root import YamlRoot
from src.dns.location import ServiceLocation
from src.dns.pihole.client import PiholeClient
from src.dns.pihole.location import resolve_pihole_location
from src.dns.pihole.secret import resolve_password


class PiholeBackend:
    """A Pi-hole v6 instance labops publishes local DNS records to."""

    name = "Pi-hole"

    def __init__(
        self, location: ServiceLocation, pihole: Pihole, password: str
    ) -> None:
        self._location = location
        self._pihole = pihole
        self._password = password

    @property
    def where(self) -> str:
        return self._location.where

    def read(self) -> tuple[list[LiveRecord], list[str]]:
        with self._client() as client:
            return client.get_hosts()

    def apply(self, desired: list[DnsRecord]) -> None:
        """Replace Pi-hole's whole record array with exactly ``desired``.

        One PATCH rather than per-record calls: the array is replaced atomically,
        so a sync cannot leave DNS half-updated if the connection drops mid-run.
        """
        records: list[tuple[IPv4Address, str]] = [
            (record.ip, record.hostname) for record in desired
        ]
        with self._client() as client:
            client.set_hosts(records)

    def _client(self) -> PiholeClient:
        return PiholeClient(
            self._location.address,
            self._password,
            scheme=self._pihole.scheme,
            port=self._pihole.port,
        )


def build_pihole_backend(
    config: YamlRoot, config_path: Path, pihole: Pihole
) -> PiholeBackend:
    """Resolve where Pi-hole is and how to authenticate, then hand back a backend.

    Both failures — an unresolvable location, no password anywhere — happen here,
    before the first request, so "you have not configured this" never arrives
    halfway through a sync.
    """
    location: ServiceLocation = resolve_pihole_location(config, pihole)
    password: str = resolve_password(config, config_path, pihole)
    return PiholeBackend(location, pihole, password)
