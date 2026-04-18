from pydantic import BaseModel
from typing import Optional, Dict

from models.inputConf.hosts import Host
from models.inputConf.settings import Settings

class YamlRoot(BaseModel):
    settings: Settings
    hosts: Optional[Dict[str, Host]] = None