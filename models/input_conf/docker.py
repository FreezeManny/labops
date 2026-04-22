from pydantic import BaseModel, model_validator, DirectoryPath
from typing import Optional, Dict

from .web_services import WebServices

class Docker(BaseModel):
    root_path: str
    stacks: Dict[str, Stack]
    
class Stack(BaseModel):
    config_path: DirectoryPath
    web_services: Optional[WebServices] = None
