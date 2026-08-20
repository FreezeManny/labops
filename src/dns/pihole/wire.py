"""The ``dns.hosts`` wire format.

Pi-hole v6 keeps local DNS records in its config tree as ``dns.hosts``: an array of
``"<ip> <name>"`` strings — exactly what the Local DNS Records page edits. That
text format is the whole reason a Pi-hole record can be *unreadable*: it is a line
of free text, not a structured entry, so anything may be in there.
"""

from ipaddress import IPv4Address

from models.dns.record import LiveRecord


def format_host_line(ip: IPv4Address, hostname: str) -> str:
    """One ``dns.hosts`` entry. labops writes one name per line, as the UI does."""
    return f"{ip} {hostname}"


def parse_hosts(lines: list[str]) -> tuple[list[LiveRecord], list[str]]:
    """Split a ``dns.hosts`` array into records and lines that made no sense.

    A single line may carry several names (``"10.0.0.1 nas nas.lab"``), which
    becomes one record per name. Unparseable lines are returned rather than
    dropped: a sync rewrites the whole array, so anything not understood here is
    about to be destroyed, and the plan has to be able to say so instead of
    quietly losing it.

    ``#`` starts a comment, as in any hosts file. Stripping it is what keeps that
    promise: splitting on whitespace alone turns ``"10.0.0.1 nas # my nas"`` into
    records named ``#`` and ``my``, which the plan then offers to delete — the one
    outcome this function exists to avoid. A line with nothing but a comment
    survives as unparsed, because a rewrite destroys it just the same.
    """
    records: list[LiveRecord] = []
    unparsed: list[str] = []

    for line in lines:
        fields: list[str] = line.split("#", 1)[0].split()
        if len(fields) < 2:
            unparsed.append(line)
            continue
        try:
            ip = IPv4Address(fields[0])
        except ValueError:
            # An IPv6 record or a typo — either way not something labops derives,
            # so it is reported rather than reinterpreted.
            unparsed.append(line)
            continue
        records.extend(LiveRecord(hostname=name, ip=ip) for name in fields[1:])

    return records, unparsed
