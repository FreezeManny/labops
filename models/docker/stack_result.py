from dataclasses import dataclass
from models.input_conf.docker import StackEntry
from ipaddress import IPv4Address

@dataclass
class StackResult:
    path: list[str]        # e.g. ["cprox", "home"] or ["lifeboat"] or ["cprox", "fr24-radar"]
    target_ip: IPv4Address # IP of the innermost container that holds the docker stack
    docker_root: str       # docker.root_path
    stack: StackEntry