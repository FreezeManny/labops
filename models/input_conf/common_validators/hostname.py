"""DNS label validation, shared by everything that turns a config string into a
hostname.

Two features do that: a web_service's ``proxy_name`` (prepended to
``settings.proxy.proxy_suffix``) and a node's name or ``dns_name`` (prepended to
``settings.dns.local_dns_suffix``). In both cases an illegal label is a failure
that would otherwise surface far from the config that caused it — a Caddyfile
Caddy refuses to load, or a record Pi-hole rejects — so both check it at validate
time, and the rule lives here so the two cannot drift apart.
"""

import re

# RFC 1035 label: letters, digits and inner hyphens, no leading/trailing hyphen.
_LABEL_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$")
LABEL_MAX_LEN = 63


def validate_hostname_label(value: str, field: str, suffix_setting: str) -> str:
    """Return ``value`` unchanged, or raise ValueError saying why it is unusable.

    ``field`` names the offending config key and ``suffix_setting`` the setting the
    label is prepended to, so the message points at the user's YAML rather than at
    this function.
    """
    if len(value) > LABEL_MAX_LEN:
        raise ValueError(
            f"{field} '{value}' is longer than {LABEL_MAX_LEN} characters "
            "(a DNS label limit)."
        )
    if not _LABEL_RE.match(value):
        raise ValueError(
            f"{field} '{value}' is not a valid hostname label. Use letters, "
            "digits and inner hyphens only — no dots, spaces or other "
            "punctuation, and no leading/trailing hyphen. It is prepended to "
            f"{suffix_setting} to form the hostname."
        )
    return value
