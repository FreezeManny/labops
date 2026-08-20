from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

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

    ``pihole_location`` is one field rather than two because ``sync`` needs an
    address and ``upgrade`` needs the thing behind it — two fields could disagree
    about which Pi-hole is meant. What you write there is therefore also what
    decides whether ``upgrade`` can run: a docker stack is upgraded by pulling an
    image rather than over SSH, and a bare IP has nothing to reach.

    Only one instance is supported. The secret store holds a single
    ``PIHOLE_PASSWORD``, so a list would quietly assume they all share it. With a
    replicating setup (nebula-sync), point labops at the primary and let it
    propagate to the rest.
    """

    local_dns_suffix: str = Field(
        ...,
        description=(
            "Appended to each node's name to form its hostname. A leading dot is "
            "optional — `.lab` and `lab` both yield `cprox.lab`."
        ),
    )
    pihole_location: Optional[str] = Field(
        None,
        description=(
            "Where Pi-hole is: a node in this config (by name or IP), a "
            "docker stack name, or a bare IP. Optional — omit it and records are "
            "still derived, so `dns list` works, while `diff`, `sync` and "
            "`upgrade` fail naming this field. Only a config node supports "
            "`dns upgrade`."
        ),
    )
    api_port: int = Field(
        80, description="The port Pi-hole's admin interface and API listen on."
    )
    api_scheme: Literal["http", "https"] = Field(
        "http",
        description=(
            "How to reach the API. `https` skips certificate verification, since "
            "Pi-hole's own certificate is self-signed."
        ),
    )
    password: Optional[str] = Field(
        None,
        description=(
            "The API password, inline. Prefer leaving this unset and putting "
            f"`{PIHOLE_PASSWORD_ENV}` in the secret store (see "
            "`settings.env_file`) — either the web-interface password or an app "
            "password from Settings → Web interface / API. Setting it here puts "
            "the secret in clear text in your config, and `dns sync` warns."
        ),
    )
    upgrade_command: str = Field(
        DEFAULT_UPGRADE_COMMAND,
        description=(
            "What `labops dns upgrade` runs on `pihole_location`. Change it to "
            "`pihole -up --check-only` to report without upgrading. Bare installs "
            "only — a containerised Pi-hole is upgraded by pulling a new image."
        ),
    )

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
