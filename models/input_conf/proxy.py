from pathlib import PurePosixPath
from pydantic import model_validator
from typing import Optional, Dict, List, Literal

from pydantic import IPvAnyNetwork

from models.input_conf.custom_types import StrictModel


class AccessList(StrictModel):
    default: bool = False
    accept: List[IPvAnyNetwork]
    deny: Optional[List[IPvAnyNetwork]] = None

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
    provider: TlsProvider = "cloudflare"
    token: Optional[str] = None


class DockerDeploy(StrictModel):
    """Docker-mode settings. Its mere presence on a ProxyDeploy selects docker
    mode; omit the whole block for a host-mode (bare `caddy`) target."""

    container: Optional[str] = None
    container_caddyfile_path: str = "/etc/caddy/Caddyfile"


# How labops reaches the Caddy process to reload it: `docker exec` into a
# container, or a bare `caddy` on the target's PATH.
DeployMode = Literal["docker", "host"]


class ProxyDeploy(StrictModel):
    target: str
    caddyfile_dest: str
    docker: Optional[DockerDeploy] = None
    reload_command: Optional[str] = None

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
    proxy_suffix: str
    tls: Optional[ProxyTls] = None
    deploy: Optional[ProxyDeploy] = None
    access_lists: Dict[str, AccessList]

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
