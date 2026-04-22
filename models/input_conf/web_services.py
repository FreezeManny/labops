from pydantic import BaseModel, model_validator, DirectoryPath, RootModel
from typing import Optional, Dict, List, Generator

class WebServices(RootModel):
    root: List[WebService]

    def __getitem__(self, item: int) -> WebService:
        return self.root[item]

class WebService(BaseModel):
    port: int
    proxy_name: Optional[str] = None
