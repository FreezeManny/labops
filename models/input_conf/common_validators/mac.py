"""The node-level ``mac`` field, shared by Host, VM and LXC.

A MAC is written a different way by everyone who prints one — Proxmox shows
``BC:24:11:AA:BB:CC``, a router's lease table ``bc-24-11-aa-bb-cc``, Cisco gear
``bc24.11aa.bbcc`` — and all of them get pasted into a config file. Accepting the
four common forms and normalising to one (lowercase, colon-separated) means the
places that consume a MAC — the magic-packet builder, the duplicate check, the
``wake --list`` table — never have to care which one was typed.

Like ``dns.py`` next door, this lives here because the field sits on all three
node types: one annotation, one error message, no drift.
"""

import re
from typing import Annotated, Optional

from pydantic import BeforeValidator

# Any of: aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff, aabb.ccdd.eeff, aabbccddeeff.
# Matched by stripping the separators first, so only the hex digits are checked.
_SEPARATORS = re.compile(r"[:.\-]")
_HEX12 = re.compile(r"^[0-9a-f]{12}$")


def normalize_mac(value: str) -> str:
    """``value`` as ``aa:bb:cc:dd:ee:ff``, or a ValueError saying why it isn't one."""
    digits: str = _SEPARATORS.sub("", value.strip()).lower()
    if not _HEX12.match(digits):
        raise ValueError(
            f"mac '{value}' is not a MAC address. Give the 6 bytes as hex — "
            "'aa:bb:cc:dd:ee:ff', 'aa-bb-cc-dd-ee-ff', 'aabb.ccdd.eeff' or "
            "'aabbccddeeff' are all accepted."
        )
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def _coerce_mac(v: object) -> object:
    # Only strings are ours to normalise; anything else falls through to pydantic,
    # which reports the type error itself.
    return normalize_mac(v) if isinstance(v, str) else v


MacAddress = Annotated[Optional[str], BeforeValidator(_coerce_mac)]
