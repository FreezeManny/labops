from dataclasses import dataclass
from models.input_conf.docker import StackEntry
from models.input_conf.creds import Creds
from ipaddress import IPv4Address


@dataclass
class StackResult:
    path:        list[str]   # e.g. ["cprox", "home"] or ["lifeboat"]
    target_ip:   IPv4Address # IP of the node that runs the stack
    docker_root: str         # docker.root_path on that node
    stack:       StackEntry
    creds:       Creds             # resolved creds (node-specific or default)