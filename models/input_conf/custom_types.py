from typing import Literal
from pydantic import BaseModel, ConfigDict

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

OSType = Literal["debian", "alpine", "redhat"]
HostType = Literal["bare-metal", "proxmox"]

