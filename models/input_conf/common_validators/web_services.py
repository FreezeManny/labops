from typing import TypeVar, Any
from ..web_services import WebService
from ..docker import Docker

T = TypeVar("T")


def check_duplicate_ws_ports(obj: T) -> T:
    all_ports: set[int] = set()

    web_services: WebService | None = getattr(obj, "web_services", None)
    if web_services:
        for ws in web_services.root:
            if ws.port in all_ports:
                raise ValueError(f"Duplicate port found: {ws.port}")
            all_ports.add(ws.port)

    docker: Docker | None = getattr(obj, "docker", None)
    if docker:
        for stack in docker.stacks.values():
            stack_ws: WebService | None = getattr(stack, "web_services", None)
            if stack_ws:
                for ws in stack_ws.root:
                    if ws.port in all_ports:
                        raise ValueError(f"Duplicate port found: {ws.port}")
                    all_ports.add(ws.port)

    return obj
