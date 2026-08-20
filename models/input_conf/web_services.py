from pydantic import BeforeValidator, Field, field_validator, RootModel
from typing import Annotated, Dict, List, Optional, Union

from .custom_types import StrictModel
from .common_validators.hostname import validate_hostname_label


class WebService(StrictModel):
    """An HTTP service a node or stack exposes.

    This is how routes get into the proxy: declaring a service next to the node
    that runs it is the whole configuration. An entry without a `proxy_name` is
    still tracked — useful for recording what a port is — but is not routed.
    """

    port: int = Field(
        ..., description="The port the service listens on, on its node's address."
    )
    proxy_name: Optional[str] = Field(
        None,
        description=(
            "Publish this service at `<proxy_name><proxy_suffix>`. Omit to track "
            "the port without routing it. The value is both a DNS label and a "
            "Caddy matcher name, so it must be a legal label."
        ),
    )
    access: Optional[List[str]] = Field(
        None,
        description=(
            "Which `settings.proxy.access_lists` may reach this service. Several "
            "lists are combined as a union. A bare string is accepted for a "
            "single list. Omit to use `settings.proxy.default_access`."
        ),
    )
    https: bool = Field(
        False,
        description=(
            "Set when the upstream itself speaks HTTPS, such as Proxmox on "
            ":8006. Renders an `https://` upstream with certificate verification "
            "skipped, since these services usually present a self-signed cert."
        ),
    )

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


def _expand_shorthand(v: object) -> object:
    """Accept the mapping shorthand ``{proxy_name: port}`` beside the list form.

    A routed service is usually nothing but a name and a port, so

    .. code-block:: yaml

        web_services:
          nas: 8080

    means the same as the long form with ``proxy_name`` and ``port`` spelled
    out. The two forms are per block, not per entry: reach for the list as soon
    as one service needs `access`, `https`, or no `proxy_name` at all.
    """
    if isinstance(v, dict):
        return [{"proxy_name": name, "port": port} for name, port in v.items()]
    return v


WebServiceEntries = Annotated[
    List[WebService],
    BeforeValidator(
        _expand_shorthand,
        # Without this the schema would advertise only the list, and an editor
        # would flag the shorthand as invalid while labops accepts it.
        json_schema_input_type=Union[List[WebService], Dict[str, int]],
    ),
]


class WebServices(RootModel):
    root: WebServiceEntries

    def __getitem__(self, item: int) -> WebService:
        return self.root[item]
