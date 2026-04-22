from pydantic import model_validator
from ipaddress import IPv4Address
from typing import Optional, Dict

from .web_services import WebServices

from .custom_types import StrictModel
from .common_validators.web_services import check_duplicate_ws_ports

class Unmanaged(StrictModel):
    name: str = ""
    ip: IPv4Address
    web_services: Optional[WebServices] = None

    @model_validator(mode="after")
    def validate_ws_ports(self) -> "Unmanaged":
        return check_duplicate_ws_ports(self)