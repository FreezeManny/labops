"""``settings.dns`` — local DNS records, and which server publishes them.

Vendor-neutral: the only thing here that knows about a particular DNS server is
the field holding its block, one module per server (models/input_conf/pihole.py).
"""

from typing import Optional

from pydantic import Field, field_validator, model_validator

from models.input_conf.custom_types import StrictModel
from models.input_conf.pihole import Pihole

# One entry per DNS server labops can publish to — the field on `Dns` holding its
# block. At most one may be set; none means records are derived but not published,
# which is what makes `dns list` work before you have a server to point at.
_BACKEND_KEYS = ("pihole",)


class Dns(StrictModel):
    """Local DNS records, and the server they are published to.

    Records are derived from the config tree — every host/VM/LXC becomes
    ``<name>.<suffix> -> ip`` — so there is no record list here. A device that
    needs a record is a node like any other (``type: bare-metal``,
    ``os: unmanaged``, an ``ip``); ``dns_name`` renames it and ``dns: false``
    excludes it. See src/dns/find.py.

    Only ``suffix`` is required. Without a server block records are still derived,
    so ``dns list`` works; ``diff``, ``sync`` and ``upgrade`` fail with a message
    naming what is missing.

    One server at a time: a second block here would be two sources of truth for the
    same records, and nothing decides which one wins.
    """

    suffix: str = Field(
        ...,
        description=(
            "Appended to each node's name to form its hostname. A leading dot is "
            "optional — `.lab` and `lab` both yield `cprox.lab`."
        ),
    )
    pihole: Optional[Pihole] = Field(
        None,
        description=(
            "Where Pi-hole is and how to reach it. Optional — omit it and records "
            "are still derived, so `dns list` works, while `diff`, `sync` and "
            "`upgrade` fail naming this block."
        ),
    )

    @model_validator(mode="after")
    def validate_one_backend(self) -> "Dns":
        """At most one server block. Zero is legal — see the class docstring."""
        given: list[str] = [
            key for key in _BACKEND_KEYS if getattr(self, key) is not None
        ]
        if len(given) > 1:
            raise ValueError(
                f"settings.dns sets {' and '.join(given)}, but labops publishes to "
                "one DNS server at a time; keep the block for the server that "
                "actually serves your records and remove the other."
            )
        return self

    @field_validator("suffix")
    @classmethod
    def _strip_leading_dot(cls, v: str) -> str:
        """``.lab`` and ``lab`` are the same zone; normalize once, at parse time.

        Every reader then joins a label onto it with exactly one dot, without
        having to remember which spelling the config used.
        """
        return v.lstrip(".")
