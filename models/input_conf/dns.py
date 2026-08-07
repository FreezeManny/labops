from typing import Literal, Optional

from pydantic import field_validator, model_validator

from models.input_conf.custom_types import StrictModel

# Key the Pi-hole API password is read from in the .env secret store
# (see settings.env_file and src/utils/env_file.py).
PIHOLE_PASSWORD_ENV = "PIHOLE_PASSWORD"

# Pi-hole installs from its own installer, not a distro repo, so `apt upgrade`
# — what `host update` / `lxc update` run — never touches it.
DEFAULT_UPGRADE_COMMAND = "pihole -up"


class Dns(StrictModel):
    """Local DNS records, published to a Pi-hole v6 instance over its REST API.

    Records are derived from the config tree — every host/VM/LXC becomes
    ``<name><local_dns_suffix> -> ip`` — so there is no record list here. A device
    that needs a record is a node like any other (``type: bare-metal``,
    ``os: unmanaged``, an ``ip``); ``dns_name`` renames it and ``dns: false``
    excludes it. See src/dns/find.py.

    Only ``local_dns_suffix`` is required. Without ``pihole_location`` records are
    still derived, so ``dns list`` works; ``diff``, ``sync`` and ``upgrade`` fail
    with a message naming the missing field.
    """

    local_dns_suffix: str
    pihole_location: Optional[str] = None
    api_port: int = 80
    api_scheme: Literal["http", "https"] = "http"
    password: Optional[str] = None
    upgrade_command: str = DEFAULT_UPGRADE_COMMAND

    @field_validator("pihole_location")
    @classmethod
    def _reject_blank(cls, v: Optional[str]) -> Optional[str]:
        # Omitting the key is allowed; writing a blank one is a mistake.
        if v is not None and not v.strip():
            raise ValueError("settings.dns.pihole_location must not be empty.")
        return v

    @model_validator(mode="after")
    def validate_upgrade_command_non_empty(self) -> "Dns":
        if not self.upgrade_command.strip():
            raise ValueError(
                "settings.dns.upgrade_command must not be empty; it is the command "
                "`labops dns upgrade` runs on the Pi-hole host."
            )
        return self

    @property
    def suffix(self) -> str:
        """``local_dns_suffix`` without a leading dot, for joining onto a label.

        ``.lab`` and ``lab`` are both accepted and mean the same zone; normalizing
        here keeps a hostname exactly one dot away from its label.
        """
        return self.local_dns_suffix.lstrip(".")
