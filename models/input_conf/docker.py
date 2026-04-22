from pydantic import BaseModel, model_validator, DirectoryPath
from typing import Optional, Dict

from .web_services import WebServices

class Docker(BaseModel):
    root_path: str
    stacks: Dict[str, StackEntry]
    
class StackEntry(BaseModel):
    config_path: DirectoryPath
    web_services: Optional[WebServices] = None
