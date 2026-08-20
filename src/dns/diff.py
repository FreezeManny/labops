from collections import defaultdict
from ipaddress import IPv4Address
from typing import Optional

from models.dns.record import DnsPlan, DnsRecord, LiveRecord, RecordUpdate


def diff_records(
    desired: list[DnsRecord],
    current: list[LiveRecord],
    unparsed: Optional[list[str]] = None,
) -> DnsPlan:
    """Compare the config's records against what the server currently serves.

    Grouped by hostname rather than compared as (hostname, ip) pairs, because a
    hostname whose address changed has to read as one update rather than as a
    delete plus an add — the difference matters when deletions are what triggers
    the confirmation prompt.

    A server may legitimately hold the same hostname more than once; such a
    hostname is an update (to the single desired address) whenever its published
    addresses are anything other than exactly the one the config asks for.
    """
    live_ips: dict[str, list[IPv4Address]] = defaultdict(list)
    for live in current:
        live_ips[live.hostname].append(live.ip)

    add: list[DnsRecord] = []
    update: list[RecordUpdate] = []
    unchanged: list[DnsRecord] = []

    for record in desired:
        published: list[IPv4Address] = live_ips.get(record.hostname, [])
        if not published:
            add.append(record)
        elif published == [record.ip]:
            unchanged.append(record)
        else:
            update.append(RecordUpdate(record=record, current_ips=published))

    wanted: set[str] = {record.hostname for record in desired}
    remove: list[LiveRecord] = [live for live in current if live.hostname not in wanted]

    return DnsPlan(
        add=add,
        update=update,
        remove=remove,
        unchanged=unchanged,
        unparsed=list(unparsed or []),
    )
