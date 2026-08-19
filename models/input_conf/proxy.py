from pathlib import Path, PurePosixPath
from pydantic import Field, field_validator, model_validator
from typing import Optional, Dict, List, Literal

from pydantic import IPvAnyNetwork

from models.input_conf.paths import ConfigRelativeFile
from models.input_conf.custom_types import StrictModel


class AccessList(StrictModel):
    """A named set of CIDRs, referenced by a web service's `access`.

    Lists are named rather than written inline so that "who may reach this" is
    declared once and reused — change the VPN range in one place and every
    service that names it follows.
    """

    default: bool = Field(
        False,
        description=(
            "Marks this as the list used by services with no explicit `access`. "
            "Exactly one list must set it."
        ),
    )
    accept: List[IPvAnyNetwork] = Field(
        ...,
        description=(
            "CIDRs allowed to reach services using this list. At least one is "
            "required. An IPv4-only list denies IPv6 clients, so a list meant to "
            "be public needs `::/0` alongside `0.0.0.0/0`."
        ),
    )
    deny: Optional[List[IPvAnyNetwork]] = Field(
        None,
        description=(
            "CIDRs blocked even when `accept` would allow them — deny wins. Use "
            "it to carve a single host out of an allowed subnet."
        ),
    )

    @model_validator(mode="after")
    def validate_accept_non_empty(self) -> "AccessList":
        if not self.accept:
            raise ValueError("an access list must define at least one 'accept' CIDR.")
        return self


# The DNS providers a user may select for the ACME DNS-01 challenge. "none" is
# the off switch (plain HTTP, no cert); every other value must have a matching
# entry in src/proxy/tls_providers.TLS_PROVIDERS, which holds the Caddy-side
# details (directive name, credential env var, required plugin). Adding a
# provider = one name here + one entry there; a test asserts the two agree.
TlsProvider = Literal["none", "cloudflare"]


class ProxyTls(StrictModel):
    """Wildcard TLS for the proxy suffix, via the provider's ACME DNS-01
    challenge.

    Omit the whole `tls:` block to serve the wildcard over plain HTTP — sensible
    for an internal suffix with no certificate.
    """

    provider: TlsProvider = Field(
        "cloudflare",
        description=(
            "One provider at a time; `none` is the off switch. The name fixes "
            "both the credential env var and the caddy-dns plugin the Caddy "
            "image must be built with — labops renders the Caddyfile, not the "
            "image, so it cannot check that the plugin is present."
        ),
    )
    token: Optional[str] = Field(
        None,
        description=(
            "The API token, inline and rendered literally into the Caddyfile — "
            "discouraged. By default labops renders a reference like "
            "`{env.CF_API_TOKEN}` that Caddy resolves from its own environment "
            "at runtime, so the secret never lands in the config or the rendered "
            "file. labops reads the same key from the secret store only to warn "
            "when it is missing."
        ),
    )


class DockerDeploy(StrictModel):
    """Docker-mode settings. Its mere presence on a ProxyDeploy selects docker
    mode; omit the whole block for a host-mode (bare `caddy`) target."""

    container: Optional[str] = Field(
        None,
        description=(
            "The container to `docker exec` into for the reload. Required in "
            "docker mode unless `reload_command` replaces the reload outright."
        ),
    )
    container_caddyfile_path: str = Field(
        "/etc/caddy/Caddyfile",
        description=(
            "Where the Caddyfile is mounted inside the container — the mount "
            "target that `caddyfile_dest` on the host maps to."
        ),
    )


# How labops reaches the Caddy process to reload it: `docker exec` into a
# container, or a bare `caddy` on the target's PATH.
DeployMode = Literal["docker", "host"]


class ProxyDeploy(StrictModel):
    """Where Caddy runs, so the rendered Caddyfile can be delivered and reloaded.

    Omit the whole block for render-only use: `proxy render` still works, and
    `sync` / `deploy` / `reload` say what is missing instead of guessing a target.
    """

    target: str = Field(
        ...,
        description=(
            "The node running Caddy — a host, VM or LXC in this config, by name, "
            "IP or vmid. Hosts and VMs are reached over SSH; an LXC is reached "
            "through its Proxmox parent with `pct`, so it needs no sshd."
        ),
    )
    caddyfile_dest: str = Field(
        ...,
        description=(
            "Absolute path the Caddyfile is written to on the target. In docker "
            "mode this is the host path that is bind-mounted into the container. "
            "Must be absolute: it is resolved on the target, where a relative "
            "path would land in the remote login directory."
        ),
    )
    docker: Optional[DockerDeploy] = Field(
        None,
        description=(
            "Present for docker mode, absent for host mode (a bare `caddy` on "
            "the target). The presence of this block is the mode switch."
        ),
    )
    reload_command: Optional[str] = Field(
        None,
        description=(
            "Replaces the whole reload command, run verbatim over SSH. Overrides "
            "the mode default; when set, `docker.container` is not required."
        ),
    )

    @property
    def mode(self) -> DeployMode:
        return "docker" if self.docker is not None else "host"

    @model_validator(mode="after")
    def validate_caddyfile_dest_absolute(self) -> "ProxyDeploy":
        # Resolved on the target, not here, so a relative path has no meaningful
        # base — Ansible would write it relative to the remote login directory.
        if not PurePosixPath(self.caddyfile_dest).is_absolute():
            raise ValueError(
                "settings.proxy.deploy.caddyfile_dest must be an absolute path on "
                f"the target (got '{self.caddyfile_dest}')."
            )
        return self

    @model_validator(mode="after")
    def validate_docker_container(self) -> "ProxyDeploy":
        if (
            self.docker is not None
            and self.reload_command is None
            and not (self.docker.container or "").strip()
        ):
            raise ValueError(
                "settings.proxy.deploy.docker.container is required in docker mode "
                "(the container name to `docker exec` into for the reload), unless "
                "reload_command overrides the default reload."
            )
        return self


class Proxy(StrictModel):
    """The Caddy reverse proxy, rendered from the config.

    There is no route list here: every `web_services` entry in the tree that
    carries a `proxy_name` becomes a route, so a service is published next to
    the node that runs it. labops owns the Caddyfile only — the image, the
    caddy-dns plugin and the environment holding the ACME token are yours.
    """

    proxy_suffix: str = Field(
        ...,
        description=(
            "The domain every route hangs off: a service named `nas` becomes "
            "`nas<proxy_suffix>`. Caddy serves it as one wildcard site."
        ),
    )
    tls: Optional[ProxyTls] = Field(
        None,
        description=(
            "Wildcard TLS for the suffix. Omit to serve plain HTTP — appropriate "
            "for an internal suffix with no certificate."
        ),
    )
    deploy: Optional[ProxyDeploy] = Field(
        None,
        description=(
            "Where Caddy runs. Omit for render-only use; `proxy sync`, `deploy` "
            "and `reload` need it."
        ),
    )
    template: Optional[ConfigRelativeFile] = Field(
        None,
        description=(
            "Render the Caddyfile from your own Jinja template instead of the "
            "built-in one. Relative to the config file, or absolute; the file "
            "must exist, so a typo fails at `labops validate` rather than "
            "part-way through a deploy. A template can replace the built-in one "
            "outright, or extend it and override only the blocks it cares about. "
            "See ansible/files/proxy/README.md."
        ),
    )
    trusted_proxies: Optional[List[IPvAnyNetwork]] = Field(
        None,
        description=(
            "CIDRs of reverse proxies (e.g. a CDN) directly in front of Caddy. "
            "When set, access-list matchers use Caddy's `client_ip` (which reads "
            "`X-Forwarded-For`) instead of `remote_ip` (the connecting socket). "
            "List only the proxy in front of Caddy — never `0.0.0.0/0`. Trusting "
            "an address that is not a proxy under your control lets anyone at "
            "that address forge their apparent IP and bypass every access list."
        ),
    )
    access_lists: Dict[str, AccessList] = Field(
        ...,
        description=(
            "Named CIDR sets that web services reference by name. Exactly one "
            "must be marked `default: true`, since a service with no explicit "
            "`access` has to resolve to something."
        ),
    )

    @field_validator("trusted_proxies", mode="after")
    @classmethod
    def validate_trusted_proxies_non_empty(
        cls, v: Optional[List[IPvAnyNetwork]],
    ) -> Optional[List[IPvAnyNetwork]]:
        if v is not None and len(v) == 0:
            raise ValueError(
                "settings.proxy.trusted_proxies must not be empty — omit the "
                "field entirely to keep using remote_ip."
            )
        return v

    @model_validator(mode="after")
    def validate_access_lists(self) -> "Proxy":
        defaults: list[str] = [
            name for name, al in self.access_lists.items() if al.default
        ]
        if len(defaults) == 0:
            raise ValueError(
                "settings.proxy.access_lists must mark exactly one list as 'default: true' "
                "(used for web_services with no explicit 'access')."
            )
        if len(defaults) > 1:
            raise ValueError(
                "only one access list may be 'default: true'; found: "
                + ", ".join(defaults)
            )
        return self

    @property
    def default_access_list(self) -> str:
        return next(name for name, al in self.access_lists.items() if al.default)
