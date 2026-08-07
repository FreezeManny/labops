from pydantic import field_validator, RootModel
from typing import Optional, List

from .custom_types import StrictModel
from .common_validators.hostname import validate_hostname_label


class WebService(StrictModel):
    port: int
    proxy_name: Optional[str] = None
    access: Optional[List[str]] = None
    # Upstream speaks HTTPS (e.g. Proxmox on :8006). Renders an https:// upstream
    # with TLS verification skipped, since such services usually present a
    # self-signed cert.
    https: bool = False

    @field_validator("access", mode="before")
    @classmethod
    def _normalize_access_to_list(cls, v: object) -> object:
        # Allow a bare string (`access: vpn`) as shorthand for a single-item list.
        return [v] if isinstance(v, str) else v

    @field_validator("proxy_name")
    @classmethod
    def _validate_proxy_name(cls, v: Optional[str]) -> Optional[str]:
        # A proxy_name is both a DNS label and a Caddy matcher name (`@<name>`),
        # so it has to satisfy the shared label rule.
        if v is None:
            return v
        return validate_hostname_label(v, "proxy_name", "settings.proxy.proxy_suffix")


class WebServices(RootModel):
    root: List[WebService]

    def __getitem__(self, item: int) -> WebService:
        return self.root[item]
