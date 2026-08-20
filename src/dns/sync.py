"""Planning what a sync would do to the configured DNS server.

Reading and diffing are one step because a plan is only meaningful against the
state it was read from. Applying is *not* here: it is the backend's own ``apply``,
called by the CLI once the plan has been shown and, when it deletes, confirmed.

Nothing about the apply depends on what was read: the desired records come purely
from the config, so applying writes the same thing regardless of what the server
currently holds — which is what makes a re-run after a failure safe.
"""

from models.dns.record import DnsPlan, DnsRecord, LiveRecord
from src.dns.backend import DnsBackend
from src.dns.diff import diff_records


def plan_sync(backend: DnsBackend, desired: list[DnsRecord]) -> DnsPlan:
    """Read the server and diff it against the config. Changes nothing."""
    current: list[LiveRecord]
    unparsed: list[str]
    current, unparsed = backend.read()
    return diff_records(desired, current, unparsed)
