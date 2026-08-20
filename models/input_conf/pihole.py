"""The ``settings.dns.pihole`` block — which Pi-hole to publish to, and how.

The config half of the Pi-hole backend, kept beside ``Dns`` rather than inside it:
``Dns`` describes local DNS in general, and everything here is Pi-hole's own. A
second DNS server gets a module like this one and a field on ``Dns``.

The code that reads it lives in src/dns/pihole/.
"""

from typing import Literal, Optional

from pydantic import Field, model_validator

from models.input_conf.custom_types import StrictModel

# Key the Pi-hole API password is read from in the .env secret store
# (see settings.env_file and src/utils/env_file.py).
PIHOLE_PASSWORD_ENV = "PIHOLE_PASSWORD"


class Pihole(StrictModel):
    """The Pi-hole instance labops publishes records to, and how to reach it.

    Where Pi-hole is stays a single answer rather than an address plus a machine:
    ``sync`` needs an address and ``upgrade`` needs the thing behind it, and two
    independent fields could disagree about which Pi-hole is meant.

    What is split out is whether Pi-hole is *installed on* a machine or *running in
    a container on* one, because that is the one thing the address cannot tell you.
    Both resolve to an address the same way — a container's records go to its host
    — but only an installation can be upgraded by running a command, so the two
    cases are separate keys rather than one string labops has to interpret.

    Only one instance is supported. The secret store holds a single
    ``PIHOLE_PASSWORD``, so a list would quietly assume they all share it. With a
    replicating setup (nebula-sync), point labops at the primary and let it
    propagate to the rest.
    """

    target: Optional[str] = Field(
        None,
        description=(
            "The machine Pi-hole is installed on — a host, VM or LXC in this "
            "config, by name or IP. It must be a node here: declare a Pi-hole "
            "labops does not otherwise manage with `os: unmanaged`, which publishes "
            "records but refuses `dns upgrade`. An LXC needs no sshd; it is reached "
            "with `pct` through its Proxmox parent. Use `docker_stack` instead for "
            "a containerised Pi-hole."
        ),
    )
    docker_stack: Optional[str] = Field(
        None,
        description=(
            "The docker stack running Pi-hole, when it is containerised. Records "
            "go to the address of the node hosting the stack, so you do not repeat "
            "it here. `dns upgrade` refuses, because a container is upgraded by "
            "pulling a new image — `labops docker stack --stack <name> update`."
        ),
    )
    port: int = Field(
        443,
        description=(
            "The port Pi-hole's admin interface and API listen on. Follows the "
            "scheme unless you set it — 443 for https, 80 for http — so neither "
            "has to be repeated after changing the other."
        ),
    )
    scheme: Literal["http", "https"] = Field(
        "https",
        description=(
            "How to reach the API. Defaults to `https` because the API password is "
            "sent in the request body, and `http` puts it on the network in clear "
            "text. Pi-hole v6 serves both out of the box. Certificate verification "
            "is skipped either way — Pi-hole's own certificate is self-signed — so "
            "`https` protects against eavesdropping rather than against a "
            "machine-in-the-middle."
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

    @model_validator(mode="after")
    def validate_exactly_one_location(self) -> "Pihole":
        """One of ``target`` / ``docker_stack``, and only one.

        A blank value counts as unset, so writing ``target: ""`` is reported as the
        missing location it is rather than resolved to nothing.

        Spelled out rather than looped over a tuple of key names: the two keys are
        also the two arguments ``resolve_service_location`` (src/dns/location.py)
        takes, and nothing checks that a list of names stays in step with them.
        """
        target: str = (self.target or "").strip()
        docker_stack: str = (self.docker_stack or "").strip()

        # Normalized, not just read: everything downstream dispatches on which key
        # is None, so a blank that only counts as unset here would still be picked
        # up as a location and resolved to nothing.
        self.target = target or None
        self.docker_stack = docker_stack or None

        if not target and not docker_stack:
            raise ValueError(
                "settings.dns.pihole needs exactly one of target: or docker_stack: "
                "— the node Pi-hole is installed on (by name or IP), or the docker "
                "stack running it. Omit the whole `pihole:` block to derive records "
                "without publishing them."
            )
        if target and docker_stack:
            raise ValueError(
                "settings.dns.pihole sets both target: and docker_stack:, but "
                "exactly one may be given — Pi-hole is either installed on a "
                "machine or running in a container on one, and the two would "
                "disagree about whether `dns upgrade` can run."
            )
        return self

    @model_validator(mode="after")
    def default_port_to_scheme(self) -> "Pihole":
        """The port follows the scheme, so changing one does not strand the other.

        A single default cannot be right for both, and the wrong one fails as a
        refused connection — which reads like a network fault rather than the
        complete-looking config it is. Keyed on whether the user wrote `port:` at
        all rather than on its value, so an explicit `port: 80` with `https` is
        still honoured: an unusual setup, but a stated one.
        """
        if "port" not in self.model_fields_set:
            self.port = 443 if self.scheme == "https" else 80
        return self
