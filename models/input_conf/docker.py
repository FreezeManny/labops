from pydantic import model_validator, DirectoryPath
from typing import Optional, Dict

from .web_services import WebServices
from .custom_types import StrictModel

class Docker(StrictModel):
    root_path: str
    stacks: Dict[str, StackEntry]
    
class StackEntry(StrictModel):
    config_path: DirectoryPath
    web_services: Optional[WebServices] = None
