"""The node-level local-DNS fields, shared by Host, VM and LXC.

Every node publishes a local DNS record — under its config name by default, or
under whatever ``dns_name`` says — and ``dns: false`` opts out. Both fields sit on
all three node types, so the ``DnsNames`` annotation below carries the shorthand
coercion (a bare string is a one-item list) and the label check once rather than
three times over.

A node's own *name* is deliberately not checked here: it is the parent's dict key,
so it is not populated until the parent's propagate validator has run, and it only
has to be a legal label when ``settings.dns`` is configured at all. ``YamlRoot``
makes that check, where both facts are known.
"""

from typing import Annotated, List, Optional

from pydantic import AfterValidator, BeforeValidator

from .hostname import validate_hostname_label


def _coerce_to_list(v: object) -> object:
    """Allow ``dns_name: nas`` as shorthand for ``dns_name: [nas]``."""
    return [v] if isinstance(v, str) else v


def _validate_labels(v: Optional[List[str]]) -> Optional[List[str]]:
    """Every entry must be a usable DNS label, and the list must not be empty.

    An empty list would publish nothing while looking like it publishes something;
    ``dns: false`` is how a node says that out loud.
    """
    if v is None:
        return v
    if not v:
        raise ValueError(
            "dns_name must give at least one label; to publish no record for this "
            "node use 'dns: false'."
        )
    seen: set[str] = set()
    for name in v:
        validate_hostname_label(name, "dns_name", "settings.dns.suffix")
        if name in seen:
            raise ValueError(f"dns_name lists '{name}' more than once.")
        seen.add(name)
    return v


DnsNames = Annotated[
    Optional[List[str]],
    BeforeValidator(_coerce_to_list),
    AfterValidator(_validate_labels),
]
