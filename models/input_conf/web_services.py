from pydantic import model_validator, field_validator, DirectoryPath, RootModel
from typing import Optional, Dict, List, Generator

from .custom_types import StrictModel


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


class WebServices(RootModel):
    root: List[WebService]

    def __getitem__(self, item: int) -> WebService:
        return self.root[item]
