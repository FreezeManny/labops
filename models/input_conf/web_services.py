import re

from pydantic import field_validator, RootModel
from typing import Optional, List

from .custom_types import StrictModel

# A proxy_name becomes both a DNS label (prepended to settings.proxy.proxy_suffix)
# and a Caddy matcher name (`@<proxy_name>`). Anything outside this shape renders
# a Caddyfile Caddy refuses to load — a failure that would otherwise only surface
# on the target during `proxy deploy`, so it is caught here instead.
_PROXY_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$")
_PROXY_NAME_MAX_LEN = 63  # RFC 1035 label limit


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
        if v is None:
            return v
        if len(v) > _PROXY_NAME_MAX_LEN:
            raise ValueError(
                f"proxy_name '{v}' is longer than {_PROXY_NAME_MAX_LEN} characters "
                "(a DNS label limit)."
            )
        if not _PROXY_NAME_RE.match(v):
            raise ValueError(
                f"proxy_name '{v}' is not a valid hostname label. Use letters, "
                "digits and inner hyphens only — no dots, spaces or other "
                "punctuation, and no leading/trailing hyphen. It is prepended to "
                "settings.proxy.proxy_suffix to form the hostname."
            )
        return v


class WebServices(RootModel):
    root: List[WebService]

    def __getitem__(self, item: int) -> WebService:
        return self.root[item]
