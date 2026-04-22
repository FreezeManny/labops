from pydantic import model_validator, DirectoryPath, RootModel
from typing import Optional, Dict, List, Generator

from .custom_types import StrictModel

class WebServices(RootModel):
    root: List[WebService]

    def __getitem__(self, item: int) -> WebService:
        return self.root[item]

class WebService(StrictModel):
    port: int
    proxy_name: Optional[str] = None
