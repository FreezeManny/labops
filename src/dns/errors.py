"""The error every DNS backend raises, so the CLI catches one type.

Config problems are ``ValueError`` as everywhere else in labops. This is the
run-time half: the server is unreachable, rejected the password, or answered with
something labops cannot use. Messages are written to be shown to the user
verbatim, so they name the instance — "connection refused" alone would not say
which one.
"""


class DnsBackendError(Exception):
    """Talking to the DNS server failed."""
